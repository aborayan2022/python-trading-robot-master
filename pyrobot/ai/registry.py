"""Model Registry and Governance for AI Quantitative Models."""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pyrobot.exceptions import ModelNotApprovedError, ModelNotFoundError
from pyrobot.logging_config import get_logger

logger = get_logger("model_registry")


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
    hyperparameters: Dict[str, any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    description: str = ""

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
        file_path = self.registry_dir / f"{meta.model_id}_{meta.version}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, indent=2)

    def register_model(self, metadata: ModelMetadata) -> None:
        """Register a new candidate model in the registry."""
        with self._lock:
            key = f"{metadata.model_id}:{metadata.version}"
            self._models[key] = metadata
            self._save_to_disk(metadata)
            logger.info("Registered model %s (type=%s, status=%s)", key, metadata.model_type, metadata.status.value)

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

            # Demote existing champion
            for key, meta in self._models.items():
                if meta.status == ModelStatus.CHAMPION and key != target_key:
                    meta.status = ModelStatus.ARCHIVED
                    self._save_to_disk(meta)
                    logger.info("Demoted previous champion %s to ARCHIVED", key)

            target = self._models[target_key]
            target.status = ModelStatus.CHAMPION
            target.approved_by = approved_by
            target.approved_at = datetime.now(timezone.utc)
            self._save_to_disk(target)
            logger.info("Promoted %s to CHAMPION by %s", target_key, approved_by)
            return target

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
