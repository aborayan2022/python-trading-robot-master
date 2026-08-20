"""Technical and Price Action Feature Extractor."""

import numpy as np
import pandas as pd
from typing import List

from pyrobot.features.base import BaseFeatureExtractor, FeatureMetadata


class TechnicalFeatures(BaseFeatureExtractor):
    """Extracts technical features including moving averages, MACD, RSI, and Bollinger Bands."""

    def __init__(
        self,
        rsi_periods: List[int] = [14, 28],
        sma_periods: List[int] = [10, 20, 50, 200],
        ema_periods: List[int] = [9, 21],
        bollinger_period: int = 20,
        bollinger_std: float = 2.0,
    ) -> None:
        self.rsi_periods = rsi_periods
        self.sma_periods = sma_periods
        self.ema_periods = ema_periods
        self.bollinger_period = bollinger_period
        self.bollinger_std = bollinger_std

    @property
    def metadata(self) -> FeatureMetadata:
        feature_names = (
            [f"rsi_{p}" for p in self.rsi_periods]
            + [f"sma_ratio_{p}" for p in self.sma_periods]
            + [f"ema_ratio_{p}" for p in self.ema_periods]
            + ["bb_upper_ratio", "bb_lower_ratio", "bb_bandwidth", "bb_percent_b"]
            + ["macd", "macd_signal", "macd_hist"]
        )
        return FeatureMetadata(
            name="technical_features",
            feature_names=feature_names,
            description="Normalized Technical analysis features (RSI, MA ratios, BB, MACD)",
            lookback_window=max(max(self.sma_periods), 200),
        )

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df)
        res = pd.DataFrame(index=df.index)
        close = df["close"]

        # 1. RSI
        for p in self.rsi_periods:
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=p, min_periods=p).mean()
            avg_loss = loss.rolling(window=p, min_periods=p).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            res[f"rsi_{p}"] = 100 - (100 / (1 + rs))

        # 2. SMA Ratios (Close / SMA - 1)
        for p in self.sma_periods:
            sma = close.rolling(window=p, min_periods=p).mean()
            res[f"sma_ratio_{p}"] = (close / sma) - 1.0

        # 3. EMA Ratios (Close / EMA - 1)
        for p in self.ema_periods:
            ema = close.ewm(span=p, adjust=False).mean()
            res[f"ema_ratio_{p}"] = (close / ema) - 1.0

        # 4. Bollinger Bands
        bb_sma = close.rolling(window=self.bollinger_period, min_periods=self.bollinger_period).mean()
        bb_std = close.rolling(window=self.bollinger_period, min_periods=self.bollinger_period).std()
        upper = bb_sma + (self.bollinger_std * bb_std)
        lower = bb_sma - (self.bollinger_std * bb_std)
        
        res["bb_upper_ratio"] = (close / upper) - 1.0
        res["bb_lower_ratio"] = (close / lower) - 1.0
        res["bb_bandwidth"] = (upper - lower) / bb_sma.replace(0, np.nan)
        res["bb_percent_b"] = (close - lower) / (upper - lower).replace(0, np.nan)

        # 5. MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        
        # Normalize MACD by close price to keep stationarity
        res["macd"] = macd / close
        res["macd_signal"] = signal / close
        res["macd_hist"] = hist / close

        return res
