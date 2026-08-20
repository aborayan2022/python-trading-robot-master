"""Quantitative Feature Engineering Package."""

from pyrobot.features.base import BaseFeatureExtractor, FeatureMetadata
from pyrobot.features.technical import TechnicalFeatures
from pyrobot.features.volatility import VolatilityFeatures
from pyrobot.features.momentum import MomentumFeatures
from pyrobot.features.regime import MarketRegimeDetector, MarketRegime, RegimeState
from pyrobot.features.engine import FeatureEngine

__all__ = [
    "BaseFeatureExtractor",
    "FeatureMetadata",
    "TechnicalFeatures",
    "VolatilityFeatures",
    "MomentumFeatures",
    "MarketRegimeDetector",
    "MarketRegime",
    "RegimeState",
    "FeatureEngine",
]
