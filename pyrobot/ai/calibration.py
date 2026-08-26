"""Probability calibration helpers for production model governance."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd


class IsotonicCalibrator:
    """Small dependency-free isotonic probability calibrator.

    The implementation uses the pair-adjacent violators algorithm on predicted
    probabilities and stores monotonic thresholds/values. It is sufficient for
    governance reports and keeps the core package free from a hard sklearn
    dependency.
    """

    def __init__(self) -> None:
        self.thresholds_: np.ndarray = np.array([])
        self.values_: np.ndarray = np.array([])
        self.is_fitted = False

    def fit(self, probabilities: np.ndarray, labels: pd.Series | np.ndarray) -> "IsotonicCalibrator":
        x = np.asarray(probabilities, dtype=float)
        y = np.asarray(labels, dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        x = x[mask]
        y = y[mask]
        if len(x) == 0:
            raise ValueError("Cannot fit calibrator with no finite samples")

        order = np.argsort(x)
        x_sorted = x[order]
        y_sorted = y[order]
        weights = np.ones_like(y_sorted)

        levels = list(y_sorted.astype(float))
        level_weights = list(weights.astype(float))
        level_x = [[float(v)] for v in x_sorted]
        i = 0
        while i < len(levels) - 1:
            if levels[i] <= levels[i + 1]:
                i += 1
                continue
            total_w = level_weights[i] + level_weights[i + 1]
            avg = (levels[i] * level_weights[i] + levels[i + 1] * level_weights[i + 1]) / total_w
            levels[i] = avg
            level_weights[i] = total_w
            level_x[i].extend(level_x[i + 1])
            del levels[i + 1]
            del level_weights[i + 1]
            del level_x[i + 1]
            i = max(0, i - 1)

        self.thresholds_ = np.array([max(xs) for xs in level_x], dtype=float)
        self.values_ = np.clip(np.array(levels, dtype=float), 0.0, 1.0)
        self.is_fitted = True
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Calibrator must be fitted before transform")
        x = np.asarray(probabilities, dtype=float)
        idx = np.searchsorted(self.thresholds_, x, side="left")
        idx = np.clip(idx, 0, len(self.values_) - 1)
        return cast(np.ndarray, np.asarray(self.values_[idx], dtype=float))

    def report(self, probabilities: np.ndarray, labels: pd.Series | np.ndarray, bins: int = 10) -> dict:
        calibrated = self.transform(probabilities)
        y = np.asarray(labels, dtype=float)
        edges = np.linspace(0.0, 1.0, bins + 1)
        rows = []
        ece = 0.0
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (calibrated >= lo) & (calibrated <= hi if hi == 1.0 else calibrated < hi)
            if not np.any(mask):
                continue
            avg_prob = float(np.mean(calibrated[mask]))
            avg_label = float(np.mean(y[mask]))
            weight = float(np.mean(mask))
            ece += weight * abs(avg_prob - avg_label)
            rows.append({
                "bin_start": float(lo),
                "bin_end": float(hi),
                "count": int(np.sum(mask)),
                "avg_probability": avg_prob,
                "empirical_rate": avg_label,
            })
        return {"expected_calibration_error": float(ece), "bins": rows}

    def save(self, path: str | Path) -> None:
        """Persist fitted calibrator to a .npz artifact (no pickle)."""
        if not self.is_fitted:
            raise RuntimeError("Calibrator must be fitted before save()")
        np.savez(
            path,
            thresholds=self.thresholds_,
            values=self.values_,
            is_fitted=np.array([self.is_fitted]),
        )

    @classmethod
    def load(cls, path: str | Path) -> "IsotonicCalibrator":
        """Restore a fitted calibrator from a .npz artifact."""
        with np.load(path, allow_pickle=False) as data:
            cal = cls()
            cal.thresholds_ = data["thresholds"].astype(np.float64)
            cal.values_ = data["values"].astype(np.float64)
            cal.is_fitted = bool(data["is_fitted"][0])
        if not cal.is_fitted:
            raise RuntimeError(f"Calibrator artifact at {path} is not fitted")
        return cal
