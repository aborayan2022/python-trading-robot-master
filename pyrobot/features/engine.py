"""Feature Engine — Central coordinator for Quantitative Feature Engineering."""

from typing import List, Optional

import pandas as pd

from pyrobot.features.base import BaseFeatureExtractor
from pyrobot.features.enhanced import EnhancedFeatures
from pyrobot.features.momentum import MomentumFeatures
from pyrobot.features.regime import MarketRegimeDetector
from pyrobot.features.technical import TechnicalFeatures
from pyrobot.features.volatility import VolatilityFeatures
from pyrobot.logging_config import get_logger

logger = get_logger("feature_engine")


class FeatureEngine:
    """Coordinates multiple feature extractors to build complete ML-ready feature matrices."""

    def __init__(self, extractors: Optional[List[BaseFeatureExtractor]] = None) -> None:
        if extractors is None:
            self.extractors: List[BaseFeatureExtractor] = [
                TechnicalFeatures(),
                VolatilityFeatures(),
                MomentumFeatures(),
                MarketRegimeDetector(),
                EnhancedFeatures(),
            ]
        else:
            self.extractors = extractors

    def add_extractor(self, extractor: BaseFeatureExtractor) -> None:
        """Add a new feature extractor to the engine."""
        self.extractors.append(extractor)

    def extract_features(
        self,
        df: pd.DataFrame,
        drop_na: bool = False,
    ) -> pd.DataFrame:
        """Generate comprehensive features DataFrame from input market data.

        Args:
            df: OHLCV DataFrame.
            drop_na: If True, drops initial rows with NaN values due to rolling windows.

        Returns:
            Concatenated DataFrame of all extracted features aligned with df index.
        """
        if df.empty:
            raise ValueError("Cannot extract features from empty DataFrame.")

        feature_frames = []
        for ext in self.extractors:
            try:
                feat = ext.extract(df)
                feature_frames.append(feat)
            except Exception as exc:
                logger.error("Extractor %s failed: %s", ext.metadata.name, exc)
                raise

        combined = pd.concat(feature_frames, axis=1)

        if drop_na:
            combined = combined.dropna()

        return combined

    def get_feature_names(self) -> List[str]:
        """List all feature column names produced by active extractors."""
        names = []
        for ext in self.extractors:
            names.extend(ext.metadata.feature_names)
        return names
