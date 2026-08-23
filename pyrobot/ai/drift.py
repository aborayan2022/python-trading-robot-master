"""Model and Feature Drift Detection using Population Stability Index (PSI) and Statistical Tests."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

import numpy as np
import pandas as pd

from pyrobot.logging_config import get_logger

logger = get_logger("drift_detector")


@dataclass
class DriftReport:
    """Evaluation summary of model/feature distribution stability."""

    is_drift_detected: bool
    max_psi: float
    feature_psi: Dict[str, float] = field(default_factory=dict)
    flagged_features: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    recommendation: str = "NO_ACTION"

    def summary(self) -> str:
        status = "DRIFT DETECTED" if self.is_drift_detected else "STABLE"
        lines = [
            f"── Model Drift Report [{status}] ──",
            f"  Max PSI:         {self.max_psi:.4f}",
            f"  Recommendation:  {self.recommendation}",
            f"  Flagged features: {', '.join(self.flagged_features) if self.flagged_features else 'None'}",
        ]
        return "\n".join(lines)


class DriftDetector:
    """Monitors distribution shifts between baseline training data and live inference data."""

    def __init__(
        self,
        psi_warning_threshold: float = 0.10,
        psi_action_threshold: float = 0.25,
        num_bins: int = 10,
    ) -> None:
        self.warning_threshold = psi_warning_threshold
        self.action_threshold = psi_action_threshold
        self.num_bins = num_bins

    def calculate_psi(self, baseline: np.ndarray, current: np.ndarray) -> float:
        """Calculate Population Stability Index between baseline and current distributions."""
        b_clean = baseline[~np.isnan(baseline)]
        c_clean = current[~np.isnan(current)]

        if len(b_clean) < 10 or len(c_clean) < 10:
            return 0.0

        # Create quantile bins from baseline
        quantiles = np.linspace(0, 100, self.num_bins + 1)
        bin_edges = np.percentile(b_clean, quantiles)
        bin_edges[0] = -np.inf
        bin_edges[-1] = np.inf

        b_counts, _ = np.histogram(b_clean, bins=bin_edges)
        c_counts, _ = np.histogram(c_clean, bins=bin_edges)

        # Convert to relative proportions with smoothing epsilon
        eps = 1e-4
        b_prop = (b_counts / len(b_clean)) + eps
        c_prop = (c_counts / len(c_clean)) + eps

        # Normalize
        b_prop /= np.sum(b_prop)
        c_prop /= np.sum(c_prop)

        psi = np.sum((c_prop - b_prop) * np.log(c_prop / b_prop))
        return float(max(0.0, psi))

    def evaluate_drift(
        self,
        baseline_df: pd.DataFrame,
        current_df: pd.DataFrame,
    ) -> DriftReport:
        """Evaluate drift across all common numerical features."""
        feature_psi: Dict[str, float] = {}
        flagged: List[str] = []
        max_psi = 0.0

        common_cols = [c for c in baseline_df.columns if c in current_df.columns and np.issubdtype(baseline_df[c].dtype, np.number)]

        for col in common_cols:
            psi = self.calculate_psi(baseline_df[col].values, current_df[col].values)
            feature_psi[col] = psi
            if psi > max_psi:
                max_psi = psi
            if psi >= self.action_threshold:
                flagged.append(col)

        is_drift = max_psi >= self.action_threshold
        if is_drift:
            rec = "RETRAIN_MODEL_AND_REDUCE_EXPOSURE"
            logger.warning("Feature drift detected! Max PSI=%.4f on features: %s", max_psi, flagged)
        elif max_psi >= self.warning_threshold:
            rec = "MONITOR_CLOSELY"
        else:
            rec = "NO_ACTION"

        return DriftReport(
            is_drift_detected=is_drift,
            max_psi=max_psi,
            feature_psi=feature_psi,
            flagged_features=flagged,
            recommendation=rec,
        )
