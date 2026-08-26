"""Walk-Forward Analysis and Purged Cross-Validation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Generator, List

import numpy as np
import pandas as pd


@dataclass
class WalkForwardSplit:
    """Represents a single in-sample (train) and out-of-sample (test) time-series fold."""

    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_indices: np.ndarray
    test_indices: np.ndarray


class WalkForwardValidator:
    """Generates Walk-Forward rolling/expanding windows with purging and embargo.

    Purging invariant (WO-2): ``purge_bars`` removes training rows whose
    timestamps lie within the purge window before ``test_start``.  This is
    essential when labels have a forward horizon — every training sample whose
    label could overlap with the first test sample must be dropped.  The rule
    is ``purge_bars >= label_horizon`` (enforced by callers, not here).
    """

    def __init__(
        self,
        n_splits: int = 5,
        train_period_days: int = 252,
        test_period_days: int = 63,
        embargo_days: int = 5,
        expanding: bool = False,
        purge_bars: int = 0,
    ) -> None:
        self.n_splits = n_splits
        self.train_period_days = train_period_days
        self.test_period_days = test_period_days
        self.embargo_days = embargo_days
        self.expanding = expanding
        self.purge_bars = purge_bars

    def split(self, df: pd.DataFrame) -> Generator[WalkForwardSplit, None, None]:
        """Generate Walk-Forward splits from a time-indexed DataFrame.

        When ``purge_bars > 0``, training rows whose timestamp is within
        ``purge_bars`` bars of ``test_start`` are dropped.  Purging is by
        **bar count** (not calendar days) so it works correctly for both
        daily and intraday data.
        """
        if not isinstance(df.index, (pd.DatetimeIndex, pd.MultiIndex)):
            raise ValueError("DataFrame index must be a DatetimeIndex or MultiIndex with timestamps.")

        # Extract timestamps
        if isinstance(df.index, pd.MultiIndex):
            timestamps = pd.to_datetime(df.index.get_level_values("timestamp" if "timestamp" in df.index.names else 1))
        else:
            timestamps = pd.to_datetime(df.index)

        unique_dates = np.sort(np.unique(timestamps.normalize()))
        total_days = len(unique_dates)

        min_required = self.train_period_days + self.embargo_days + self.test_period_days
        if total_days < min_required:
            raise ValueError(
                f"Insufficient data: have {total_days} unique days, require at least {min_required} days."
            )

        step = max(1, (total_days - min_required) // max(1, self.n_splits - 1)) if self.n_splits > 1 else self.test_period_days

        for i in range(self.n_splits):
            train_start_idx = 0 if self.expanding else (i * step)
            train_end_idx = train_start_idx + self.train_period_days if not self.expanding else (self.train_period_days + i * step)

            test_start_idx = train_end_idx + self.embargo_days
            test_end_idx = test_start_idx + self.test_period_days

            if test_end_idx > total_days:
                test_end_idx = total_days
                if test_start_idx >= test_end_idx:
                    break

            t_train_start = unique_dates[train_start_idx]
            t_train_end = unique_dates[train_end_idx - 1]
            t_test_start = unique_dates[test_start_idx]
            t_test_end = unique_dates[test_end_idx - 1]

            # Boolean masks — calendar-day granularity (embargo)
            train_mask = (timestamps >= t_train_start) & (timestamps <= t_train_end)
            test_mask = (timestamps >= t_test_start) & (timestamps <= t_test_end)

            train_idx = np.where(train_mask)[0]
            test_idx = np.where(test_mask)[0]

            # Bar-level purging: drop training rows whose index position is within
            # purge_bars of test_start.  This prevents label leakage when the
            # label horizon extends beyond the calendar embargo gap.
            # Purging is by bar count (not calendar days) so it works correctly
            # for both daily and intraday data.
            if self.purge_bars > 0 and len(train_idx) > 0 and len(test_idx) > 0:
                test_start_pos = test_idx[0]
                purge_boundary = test_start_pos - self.purge_bars
                train_idx = train_idx[train_idx < purge_boundary]

            yield WalkForwardSplit(
                fold_index=i,
                train_start=t_train_start,
                train_end=t_train_end,
                test_start=t_test_start,
                test_end=t_test_end,
                train_indices=train_idx,
                test_indices=test_idx,
            )


@dataclass
class WalkForwardResult:
    """Aggregated out-of-sample results of a walk-forward evaluation."""

    fold_scores: List[float] = field(default_factory=list)
    oos_score: float = 0.0
    oos_predictions: np.ndarray = field(default_factory=lambda: np.array([]))
    oos_labels: np.ndarray = field(default_factory=lambda: np.array([]))
    oos_probabilities: np.ndarray = field(default_factory=lambda: np.array([]))

    def summary(self) -> dict:
        return {
            "n_folds": len(self.fold_scores),
            "fold_scores": [round(float(s), 6) for s in self.fold_scores],
            "oos_score": round(float(self.oos_score), 6),
            "n_oos_predictions": int(len(self.oos_predictions)),
        }


def run_walk_forward(
    features: pd.DataFrame,
    labels: pd.Series,
    model_factory: Callable[[], Any],
    train_fn: Callable[[Any, pd.DataFrame, pd.Series], None],
    predict_fn: Callable[[Any, pd.DataFrame], np.ndarray],
    metric_fn: Callable[[pd.Series, np.ndarray], float],
    *,
    n_splits: int = 5,
    train_period_days: int = 252,
    test_period_days: int = 63,
    embargo_days: int = 5,
    expanding: bool = True,
    purge_bars: int = 0,
    proba_fn: Callable[[Any, pd.DataFrame], np.ndarray] | None = None,
) -> WalkForwardResult:
    """Run a full walk-forward evaluation: re-fit per fold, score out-of-sample.

    Generic and model-agnostic — the caller supplies how to build, train, and
    predict with a model plus the scoring function, so any estimator (including
    numpy-only models) can be validated without leaking future data.

    Args:
        features: Feature matrix indexed by timestamp (or (symbol, timestamp)).
        labels: Aligned target series (same index as features).
        model_factory: Zero-arg callable returning a fresh untrained model.
        train_fn: (model, X_train, y_train) -> None (fits in place).
        predict_fn: (model, X_test) -> np.ndarray of predictions.
        metric_fn: (y_true, y_pred) -> float (higher is better).
        n_splits/train_period_days/test_period_days/embargo_days/expanding:
            Fold geometry forwarded to WalkForwardValidator.
        purge_bars: Number of bars before test_start to remove from training
            data.  Invariant: ``purge_bars >= label_horizon`` to prevent
            label leakage across folds.
        proba_fn: Optional (model, X_test) -> np.ndarray of probabilities.
            When provided, OOS probabilities are collected alongside
            predictions for downstream calibration and ECE evaluation.
            The returned array must have shape (n_samples, n_classes) or
            (n_samples,) for binary positive-class probabilities.

    Returns:
        WalkForwardResult with per-fold scores, the aggregated OOS score computed
        ONCE over the concatenated out-of-sample predictions, and the predictions.
    """
    df = features.copy()
    validator = WalkForwardValidator(
        n_splits=n_splits,
        train_period_days=train_period_days,
        test_period_days=test_period_days,
        embargo_days=embargo_days,
        expanding=expanding,
        purge_bars=purge_bars,
    )

    result = WalkForwardResult()
    oos_preds: List[np.ndarray] = []
    oos_labels: List[np.ndarray] = []
    oos_probas: List[np.ndarray] = []

    for split in validator.split(df):
        train_idx = split.train_indices
        test_idx = split.test_indices
        if len(train_idx) == 0 or len(test_idx) == 0:
            continue

        model = model_factory()
        train_fn(model, df.iloc[train_idx], labels.iloc[train_idx])
        preds = np.asarray(predict_fn(model, df.iloc[test_idx]))

        fold_score = float(metric_fn(labels.iloc[test_idx], preds))
        result.fold_scores.append(fold_score)

        oos_preds.append(preds)
        oos_labels.append(labels.iloc[test_idx].to_numpy())

        if proba_fn is not None:
            proba = np.asarray(proba_fn(model, df.iloc[test_idx]))
            # Accept (n,) or (n, 2) — extract positive-class column
            if proba.ndim == 2 and proba.shape[1] >= 2:
                proba = proba[:, 1]
            oos_probas.append(proba)

    if oos_preds:
        result.oos_predictions = np.concatenate(oos_preds)
        result.oos_labels = np.concatenate(oos_labels)
        result.oos_score = float(metric_fn(pd.Series(result.oos_labels), result.oos_predictions))
        if oos_probas:
            result.oos_probabilities = np.concatenate(oos_probas)

    return result
