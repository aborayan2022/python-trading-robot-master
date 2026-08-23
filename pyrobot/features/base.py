"""Base abstractions for Quantitative Feature Engineering."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

import pandas as pd


@dataclass
class FeatureMetadata:
    """Metadata describing a generated feature set."""

    name: str
    feature_names: List[str]
    description: str = ""
    lookback_window: int = 1
    requires_columns: List[str] = field(default_factory=lambda: ["open", "high", "low", "close", "volume"])
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseFeatureExtractor(ABC):
    """Abstract base class for all feature extractors."""

    @property
    @abstractmethod
    def metadata(self) -> FeatureMetadata:
        """Metadata for this feature extractor."""
        ...

    @abstractmethod
    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract features from the input OHLCV DataFrame.

        Must preserve index and avoid any lookahead bias (e.g. no forward-looking shifts).

        Args:
            df: Input DataFrame with standard columns ['open', 'high', 'low', 'close', 'volume'].

        Returns:
            DataFrame containing calculated feature columns.
        """
        ...

    def validate_input(self, df: pd.DataFrame) -> None:
        """Validate that input DataFrame satisfies minimum requirements."""
        if df.empty:
            raise ValueError("Input DataFrame is empty.")

        # Case-insensitive column matching
        lower_cols = {c.lower(): c for c in df.columns}
        for req in self.metadata.requires_columns:
            if req.lower() not in lower_cols:
                raise ValueError(
                    f"Feature extractor {self.metadata.name!r} requires column {req!r}, "
                    f"available columns: {list(df.columns)}"
                )
