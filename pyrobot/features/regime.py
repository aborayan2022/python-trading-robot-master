"""Market Regime Detection and Classification."""

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from pyrobot.features.base import BaseFeatureExtractor, FeatureMetadata


class MarketRegime(Enum):
    """Enumeration of recognizable market regimes."""

    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    CRISIS = "CRISIS"


@dataclass
class RegimeState:
    """Snapshot of detected regime and associated metrics."""

    regime: MarketRegime
    confidence: float
    trend_score: float
    volatility_score: float
    recommended_strategy_type: str


class MarketRegimeDetector(BaseFeatureExtractor):
    """Detects market regimes using moving average alignment, volatility percentiles, and trend strength."""

    def __init__(
        self,
        trend_short: int = 20,
        trend_long: int = 50,
        vol_lookback: int = 60,
        vol_high_threshold_pct: float = 0.85,
    ) -> None:
        self.trend_short = trend_short
        self.trend_long = trend_long
        self.vol_lookback = vol_lookback
        self.vol_high_threshold_pct = vol_high_threshold_pct

    @property
    def metadata(self) -> FeatureMetadata:
        return FeatureMetadata(
            name="regime_features",
            feature_names=[
                "regime_code",
                "regime_confidence",
                "trend_strength",
                "vol_percentile",
            ],
            description="Market regime classification (Bull=1, Bear=2, Sideways=3, HighVol=4, Crisis=5)",
            lookback_window=max(self.trend_long, self.vol_lookback),
        )

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df)
        res = pd.DataFrame(index=df.index)
        close = df["close"]

        # 1. Moving averages for trend
        sma_short = close.rolling(self.trend_short, min_periods=self.trend_short).mean()
        sma_long = close.rolling(self.trend_long, min_periods=self.trend_long).mean()
        trend_diff = (sma_short - sma_long) / sma_long

        # 2. Volatility and Volatility Percentile
        log_ret = np.log(close / close.shift(1))
        vol = log_ret.rolling(20, min_periods=20).std()

        # Calculate percentile of current volatility over vol_lookback window
        def calc_pct(s: pd.Series) -> float:
            if s.empty or np.isnan(s.iloc[-1]):
                return np.nan
            val = s.iloc[-1]
            return float((s <= val).mean())

        vol_pct = vol.rolling(self.vol_lookback, min_periods=20).apply(calc_pct, raw=False)

        res["trend_strength"] = trend_diff
        res["vol_percentile"] = vol_pct

        # 3. Classify regimes row-by-row
        # Codes: 1: BULL, 2: BEAR, 3: SIDEWAYS, 4: HIGH_VOLATILITY, 5: CRISIS
        regime_codes = []
        confidences = []

        for t_diff, v_p in zip(trend_diff, vol_pct):
            if np.isnan(t_diff) or np.isnan(v_p):
                regime_codes.append(np.nan)
                confidences.append(np.nan)
                continue

            if v_p >= 0.95 and t_diff < -0.05:
                regime_codes.append(5)  # CRISIS
                confidences.append(min(1.0, (v_p - 0.95) * 10 + 0.8))
            elif v_p >= self.vol_high_threshold_pct:
                regime_codes.append(4)  # HIGH_VOLATILITY
                confidences.append(min(1.0, (v_p - 0.85) * 5 + 0.7))
            elif t_diff > 0.02:
                regime_codes.append(1)  # BULL
                confidences.append(min(1.0, abs(t_diff) * 10 + 0.6))
            elif t_diff < -0.02:
                regime_codes.append(2)  # BEAR
                confidences.append(min(1.0, abs(t_diff) * 10 + 0.6))
            else:
                regime_codes.append(3)  # SIDEWAYS
                confidences.append(0.7)

        res["regime_code"] = regime_codes
        res["regime_confidence"] = confidences

        return res

    def get_current_regime(self, df: pd.DataFrame) -> RegimeState:
        """Evaluate latest market data and return current regime state."""
        extracted = self.extract(df)
        last_row = extracted.iloc[-1]

        code = last_row.get("regime_code", 3)
        conf = last_row.get("regime_confidence", 0.5)
        trend = last_row.get("trend_strength", 0.0)
        vol_pct = last_row.get("vol_percentile", 0.5)

        if np.isnan(code):
            regime = MarketRegime.SIDEWAYS
            conf = 0.5
        elif code == 1:
            regime = MarketRegime.BULL
        elif code == 2:
            regime = MarketRegime.BEAR
        elif code == 4:
            regime = MarketRegime.HIGH_VOLATILITY
        elif code == 5:
            regime = MarketRegime.CRISIS
        else:
            regime = MarketRegime.SIDEWAYS

        rec_strategy = {
            MarketRegime.BULL: "TREND_FOLLOWING",
            MarketRegime.BEAR: "DEFENSIVE_SHORT",
            MarketRegime.SIDEWAYS: "MEAN_REVERSION",
            MarketRegime.HIGH_VOLATILITY: "REDUCE_SIZE_MOMENTUM",
            MarketRegime.CRISIS: "CAPITAL_PRESERVATION",
        }[regime]

        return RegimeState(
            regime=regime,
            confidence=float(conf) if not np.isnan(conf) else 0.5,
            trend_score=float(trend) if not np.isnan(trend) else 0.0,
            volatility_score=float(vol_pct) if not np.isnan(vol_pct) else 0.5,
            recommended_strategy_type=rec_strategy,
        )

    def detect(self, df: pd.DataFrame) -> RegimeState:
        """Alias for get_current_regime."""
        return self.get_current_regime(df)
