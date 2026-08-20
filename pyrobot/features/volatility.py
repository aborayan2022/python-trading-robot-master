"""Volatility and Dispersion Feature Extractor."""

import numpy as np
import pandas as pd
from typing import List

from pyrobot.features.base import BaseFeatureExtractor, FeatureMetadata


class VolatilityFeatures(BaseFeatureExtractor):
    """Extracts volatility metrics including ATR, Realized Volatility, and Parkinson Volatility."""

    def __init__(
        self,
        atr_periods: List[int] = [14, 30],
        rv_periods: List[int] = [10, 20, 60],
    ) -> None:
        self.atr_periods = atr_periods
        self.rv_periods = rv_periods

    @property
    def metadata(self) -> FeatureMetadata:
        feature_names = (
            [f"atr_pct_{p}" for p in self.atr_periods]
            + [f"realized_vol_{p}" for p in self.rv_periods]
            + ["parkinson_vol_20", "garman_klass_vol_20", "hl_range_pct"]
        )
        return FeatureMetadata(
            name="volatility_features",
            feature_names=feature_names,
            description="Normalized Volatility features (ATR %, Realized Vol, Parkinson/Garman-Klass)",
            lookback_window=max(max(self.rv_periods), max(self.atr_periods)),
        )

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df)
        res = pd.DataFrame(index=df.index)
        
        high = df["high"]
        low = df["low"]
        close = df["close"]
        open_ = df["open"]

        # Log returns
        log_ret = np.log(close / close.shift(1))

        # 1. ATR percentage
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        for p in self.atr_periods:
            atr = tr.rolling(window=p, min_periods=p).mean()
            res[f"atr_pct_{p}"] = atr / close

        # 2. Realized Volatility (annualized: sqrt(252) * rolling std of log returns)
        for p in self.rv_periods:
            res[f"realized_vol_{p}"] = log_ret.rolling(window=p, min_periods=p).std() * np.sqrt(252)

        # 3. Parkinson Volatility (based on High/Low)
        # formula: sqrt( 1 / (4 * ln(2) * N) * sum( ln(H/L)^2 ) ) * sqrt(252)
        hl_log_sq = (np.log(high / low.replace(0, np.nan))) ** 2
        p_vol_20 = np.sqrt(hl_log_sq.rolling(20, min_periods=20).mean() / (4 * np.log(2))) * np.sqrt(252)
        res["parkinson_vol_20"] = p_vol_20

        # 4. Garman-Klass Volatility (combines OHLC)
        # formula: 0.5 * ln(H/L)^2 - (2*ln(2)-1) * ln(C/O)^2
        co_log_sq = (np.log(close / open_.replace(0, np.nan))) ** 2
        gk = 0.5 * hl_log_sq - (2 * np.log(2) - 1) * co_log_sq
        res["garman_klass_vol_20"] = np.sqrt(gk.rolling(20, min_periods=20).mean().clip(lower=0)) * np.sqrt(252)

        # 5. Daily High-Low Range Percentage
        res["hl_range_pct"] = (high - low) / close

        return res
