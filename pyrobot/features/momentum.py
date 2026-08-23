"""Momentum and Volume-Price Action Feature Extractor."""

from typing import List

import numpy as np
import pandas as pd

from pyrobot.features.base import BaseFeatureExtractor, FeatureMetadata


class MomentumFeatures(BaseFeatureExtractor):
    """Extracts momentum, return horizons, and volume features."""

    def __init__(
        self,
        return_periods: List[int] = [1, 3, 5, 10, 20],
        volume_ma_periods: List[int] = [5, 20],
    ) -> None:
        self.return_periods = return_periods
        self.volume_ma_periods = volume_ma_periods

    @property
    def metadata(self) -> FeatureMetadata:
        feature_names = (
            [f"return_{p}" for p in self.return_periods]
            + [f"log_return_{p}" for p in self.return_periods]
            + [f"vol_ratio_{p}" for p in self.volume_ma_periods]
            + ["return_acceleration_5_20", "vwap_deviation"]
        )
        return FeatureMetadata(
            name="momentum_features",
            feature_names=feature_names,
            description="Normalized Momentum, Multi-horizon Returns, and Relative Volume",
            lookback_window=max(max(self.return_periods), max(self.volume_ma_periods)),
        )

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df)
        res = pd.DataFrame(index=df.index)

        close = df["close"]
        volume = df["volume"]

        # 1. Multi-horizon returns and log returns
        for p in self.return_periods:
            res[f"return_{p}"] = close.pct_change(p)
            res[f"log_return_{p}"] = np.log(close / close.shift(p))

        # 2. Volume ratios (Volume / Volume MA - 1)
        for p in self.volume_ma_periods:
            v_ma = volume.rolling(window=p, min_periods=p).mean()
            res[f"vol_ratio_{p}"] = (volume / v_ma.replace(0, np.nan)) - 1.0

        # 3. Momentum acceleration (e.g. Return 5 minus Return 20)
        ret5 = close.pct_change(5)
        ret20 = close.pct_change(20)
        res["return_acceleration_5_20"] = ret5 - ret20

        # 4. VWAP deviation (Rolling 20 periods)
        hlc3 = (df["high"] + df["low"] + df["close"]) / 3.0
        rolling_vp = (hlc3 * volume).rolling(20, min_periods=20).sum()
        rolling_v = volume.rolling(20, min_periods=20).sum()
        vwap = rolling_vp / rolling_v.replace(0, np.nan)
        res["vwap_deviation"] = (close / vwap) - 1.0

        return res
