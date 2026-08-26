"""Model Registry and Governance for AI Quantitative Models."""

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyrobot.ai.models import BaseQuantModel, model_class_for_type
from pyrobot.exceptions import ModelNotApprovedError, ModelNotFoundError
from pyrobot.logging_config import get_logger

logger = get_logger("model_registry")

_SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


class ArtifactIntegrityError(Exception):
    """Raised when a stored model artifact is missing or fails its checksum."""


class ModelStatus(str, Enum):
    """Lifecycle status of an AI/ML model."""

    CANDIDATE = "CANDIDATE"       # Initial trained model under research evaluation
    CHALLENGER = "CHALLENGER"     # Shadow mode model running in parallel without live orders
    CHAMPION = "CHAMPION"         # Active production model approved for live signals
    ARCHIVED = "ARCHIVED"         # Deprecated / retired model


@dataclass
class ModelMetadata:
    """Metadata describing a registered quantitative ML model."""

    model_id: str
    version: str
    model_type: str
    target_variable: str
    features: List[str]
    training_start: str
    training_end: str
    status: ModelStatus = ModelStatus.CANDIDATE
    oos_metrics: Dict[str, float] = field(default_factory=dict)
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    description: str = ""
    artifact_path: Optional[str] = None
    artifact_sha256: Optional[str] = None
    calibration_path: Optional[str] = None
    calibration_sha256: Optional[str] = None
    n_trials: int = 1

    def to_dict(self) -> Dict:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "model_type": self.model_type,
            "target_variable": self.target_variable,
            "features": self.features,
            "training_start": self.training_start,
            "training_end": self.training_end,
            "status": self.status.value,
            "oos_metrics": self.oos_metrics,
            "hyperparameters": self.hyperparameters,
            "created_at": self.created_at.isoformat(),
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "description": self.description,
            "artifact_path": self.artifact_path,
            "artifact_sha256": self.artifact_sha256,
            "calibration_path": self.calibration_path,
            "calibration_sha256": self.calibration_sha256,
            "n_trials": self.n_trials,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ModelMetadata":
        approved_at = None
        if data.get("approved_at"):
            approved_at = datetime.fromisoformat(data["approved_at"])

        return cls(
            model_id=data["model_id"],
            version=data["version"],
            model_type=data["model_type"],
            target_variable=data["target_variable"],
            features=data["features"],
            training_start=data["training_start"],
            training_end=data["training_end"],
            status=ModelStatus(data.get("status", "CANDIDATE")),
            oos_metrics=data.get("oos_metrics", {}),
            hyperparameters=data.get("hyperparameters", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            approved_by=data.get("approved_by"),
            approved_at=approved_at,
            description=data.get("description", ""),
            artifact_path=data.get("artifact_path"),
            artifact_sha256=data.get("artifact_sha256"),
            calibration_path=data.get("calibration_path"),
            calibration_sha256=data.get("calibration_sha256"),
            n_trials=data.get("n_trials", 1),
        )


class ModelRegistry:
    """Thread-safe registry for AI/ML models with Champion/Challenger governance."""

    def __init__(self, registry_dir: Optional[Path | str] = "data/models") -> None:
        self.registry_dir = Path(registry_dir) if registry_dir else None
        self._models: Dict[str, ModelMetadata] = {}
        self._lock = threading.RLock()

        if self.registry_dir:
            self.registry_dir.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self.registry_dir:
            return
        for json_file in self.registry_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    meta = ModelMetadata.from_dict(json.load(f))
                    key = f"{meta.model_id}:{meta.version}"
                    self._models[key] = meta
            except Exception as e:
                logger.warning("Failed to load model metadata %s: %s", json_file, e)

    def _save_to_disk(self, meta: ModelMetadata) -> None:
        if not self.registry_dir:
            return
        safe_name = self._safe_filename(meta.model_id, meta.version)
        file_path = self.registry_dir / f"{safe_name}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2)

    @staticmethod
    def _safe_filename(model_id: str, version: str) -> str:
        """Filesystem-safe artifact name (ids sanitized against path tricks)."""
        return f"{_SAFE_ID.sub('_', model_id)}_{_SAFE_ID.sub('_', version)}"

    def register_model(
        self,
        metadata: ModelMetadata,
        model: Optional[BaseQuantModel] = None,
        calibrator: Optional[Any] = None,
    ) -> None:
        """Register a candidate model; optionally persist its fitted artifact.

        Args:
            metadata: Descriptive metadata for governance.
            model: Fitted model instance. When provided, its parameters are
                written to a .npz artifact next to the metadata and the SHA-256
                checksum is recorded so load_model() can verify integrity.
            calibrator: Optional fitted IsotonicCalibrator. When provided, it
                is persisted alongside the model artifact as a separate .npz
                file with its own SHA-256 checksum.
        """
        with self._lock:
            key = f"{metadata.model_id}:{metadata.version}"
            self._models[key] = metadata

            if model is not None:
                if not getattr(model, "is_fitted", False):
                    raise ValueError(
                        f"Cannot register unfitted model {key} — fit() it first"
                    )
                if self.registry_dir is not None:
                    safe_name = self._safe_filename(metadata.model_id, metadata.version)
                    artifact_path = self.registry_dir / f"{safe_name}.npz"
                    model.save(artifact_path)
                    metadata.artifact_path = str(artifact_path)
                    metadata.artifact_sha256 = self._sha256(artifact_path)

            if calibrator is not None and self.registry_dir is not None:
                if not getattr(calibrator, "is_fitted", False):
                    raise ValueError(
                        f"Cannot register unfitted calibrator for {key} — fit() it first"
                    )
                safe_name = self._safe_filename(metadata.model_id, metadata.version)
                calib_path = self.registry_dir / f"{safe_name}.calib.npz"
                calibrator.save(calib_path)
                metadata.calibration_path = str(calib_path)
                metadata.calibration_sha256 = self._sha256(calib_path)

            self._save_to_disk(metadata)
            logger.info(
                "Registered model %s (type=%s, status=%s, artifact=%s, calibrator=%s)",
                key, metadata.model_type, metadata.status.value,
                "yes" if metadata.artifact_path else "no",
                "yes" if metadata.calibration_path else "no",
            )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def load_model(self, model_id: str, version: str) -> BaseQuantModel:
        """Load a fitted model artifact by id and version, verifying its checksum."""
        meta = self.get_model(model_id, version)
        if not meta.artifact_path:
            raise ArtifactIntegrityError(
                f"Model {model_id}:{version} has no stored artifact "
                "(registered metadata-only)"
            )
        artifact = Path(meta.artifact_path)
        if not artifact.exists():
            raise ArtifactIntegrityError(
                f"Artifact for {model_id}:{version} is missing: {artifact}"
            )
        if meta.artifact_sha256 and self._sha256(artifact) != meta.artifact_sha256:
            raise ArtifactIntegrityError(
                f"Artifact checksum mismatch for {model_id}:{version} — tampered or corrupted"
            )
        model_cls = model_class_for_type(meta.model_type)
        return model_cls.load(artifact)

    def load_calibrator(self, model_id: str, version: str):
        """Load a fitted calibrator artifact by id and version, verifying its checksum.

        Returns None if no calibrator is registered for this model (graceful
        degradation — the caller should log a warning).
        """
        from pyrobot.ai.calibration import IsotonicCalibrator

        meta = self.get_model(model_id, version)
        if not meta.calibration_path:
            return None
        calib_path = Path(meta.calibration_path)
        if not calib_path.exists():
            logger.warning(
                "Calibrator artifact missing for %s:%s at %s",
                model_id, version, calib_path,
            )
            return None
        if meta.calibration_sha256 and self._sha256(calib_path) != meta.calibration_sha256:
            raise ArtifactIntegrityError(
                f"Calibrator checksum mismatch for {model_id}:{version} — tampered or corrupted"
            )
        return IsotonicCalibrator.load(calib_path)

    def get_model(self, model_id: str, version: str) -> ModelMetadata:
        """Retrieve model metadata by ID and version."""
        with self._lock:
            key = f"{model_id}:{version}"
            if key not in self._models:
                raise ModelNotFoundError(f"Model {key} not found in registry")
            return self._models[key]

    def promote_to_champion(self, model_id: str, version: str, approved_by: str) -> ModelMetadata:
        """Promote a model to Champion status (demotes any previous champion to challenger/archived)."""
        with self._lock:
            target_key = f"{model_id}:{version}"
            if target_key not in self._models:
                raise ModelNotFoundError(f"Model {target_key} not found in registry")
            target = self._models[target_key]
            self._validate_champion_candidate(target)

            # Demote existing champion
            for key, meta in self._models.items():
                if meta.status == ModelStatus.CHAMPION and key != target_key:
                    meta.status = ModelStatus.ARCHIVED
                    self._save_to_disk(meta)
                    logger.info("Demoted previous champion %s to ARCHIVED", key)

            target.status = ModelStatus.CHAMPION
            target.approved_by = approved_by
            target.approved_at = datetime.now(timezone.utc)
            self._save_to_disk(target)
            logger.info("Promoted %s to CHAMPION by %s", target_key, approved_by)
            return target

    def _validate_champion_candidate(self, meta: ModelMetadata) -> None:
        """Enforce production model governance before champion promotion."""
        if not meta.artifact_path or not meta.artifact_sha256:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: missing artifact"
            )
        artifact = Path(meta.artifact_path)
        if not artifact.exists() or self._sha256(artifact) != meta.artifact_sha256:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: artifact integrity failed"
            )
        required = {
            "oos_accuracy",
            "buy_hold_accuracy",
            "sma_accuracy",
            "expected_calibration_error",
            "oos_samples",
            # WO-4: Economic metrics are mandatory for champion promotion.
            "net_pnl_after_costs",
            "sharpe",
            "profit_factor",
            "n_trades",
            "ev_per_trade",
        }
        missing = required.difference(meta.oos_metrics)
        if missing:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: missing metrics {sorted(missing)}"
            )
        baseline = max(meta.oos_metrics["buy_hold_accuracy"], meta.oos_metrics["sma_accuracy"])
        if meta.oos_metrics["oos_accuracy"] <= baseline:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: no OOS edge over baselines"
            )
        if meta.oos_metrics["expected_calibration_error"] > 0.15:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: calibration error too high"
            )
        # WO-4: Economic gate — a model that cannot show economics cannot be champion.
        if meta.oos_metrics["net_pnl_after_costs"] < 0:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: negative net PnL after costs"
            )
        if meta.oos_metrics["ev_per_trade"] <= 0:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: EV per trade ≤ 0"
            )
        if meta.oos_metrics["n_trades"] < 10:
            raise ModelNotApprovedError(
                f"Model {meta.model_id}:{meta.version} cannot be champion: too few trades ({meta.oos_metrics['n_trades']})"
            )

    def promote_to_challenger(self, model_id: str, version: str) -> ModelMetadata:
        """Promote a model to Challenger (shadow mode) status."""
        with self._lock:
            key = f"{model_id}:{version}"
            if key not in self._models:
                raise ModelNotFoundError(f"Model {key} not found in registry")

            target = self._models[key]
            target.status = ModelStatus.CHALLENGER
            self._save_to_disk(target)
            logger.info("Promoted %s to CHALLENGER", key)
            return target

    def get_champion(self) -> Optional[ModelMetadata]:
        """Return the current Champion model metadata, if any."""
        with self._lock:
            for meta in self._models.values():
                if meta.status == ModelStatus.CHAMPION:
                    return meta
            return None

    def get_challengers(self) -> List[ModelMetadata]:
        """Return list of active Challenger models."""
        with self._lock:
            return [m for m in self._models.values() if m.status == ModelStatus.CHALLENGER]

    def list_models(self) -> List[ModelMetadata]:
        """Return all registered models."""
        with self._lock:
            return list(self._models.values())
