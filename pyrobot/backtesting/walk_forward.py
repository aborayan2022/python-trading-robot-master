"""Walk-Forward Analysis and Purged Cross-Validation."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Generator
import pandas as pd
import numpy as np


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
    """Generates Walk-Forward rolling/expanding windows with purging and embargo."""

    def __init__(
        self,
        n_splits: int = 5,
        train_period_days: int = 252,
        test_period_days: int = 63,
        embargo_days: int = 5,
        expanding: bool = False,
    ) -> None:
        self.n_splits = n_splits
        self.train_period_days = train_period_days
        self.test_period_days = test_period_days
        self.embargo_days = embargo_days
        self.expanding = expanding

    def split(self, df: pd.DataFrame) -> Generator[WalkForwardSplit, None, None]:
        """Generate Walk-Forward splits from a time-indexed DataFrame."""
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

            # Boolean masks
            train_mask = (timestamps >= t_train_start) & (timestamps <= t_train_end)
            test_mask = (timestamps >= t_test_start) & (timestamps <= t_test_end)

            train_idx = np.where(train_mask)[0]
            test_idx = np.where(test_mask)[0]

            yield WalkForwardSplit(
                fold_index=i,
                train_start=t_train_start,
                train_end=t_train_end,
                test_start=t_test_start,
                test_end=t_test_end,
                train_indices=train_idx,
                test_indices=test_idx,
            )
