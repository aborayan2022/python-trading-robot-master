"""Enhanced Feature Extractor — Advanced Momentum, Volatility Regime, and Calendar Features.

Per the consultant's directive (31 Aug 2026), the base features (RSI, MACD, Bollinger,
Parkinson/Garman-Klass vol, regime detection) are "already advanced but not sufficient."
This module adds:
  - Momentum divergence & acceleration features
  - Volatility regime duration & transition features
  - Calendar-based features (day-of-week, month-end effects)
"""

from typing import List

import numpy as np
import pandas as pd

from pyrobot.features.base import BaseFeatureExtractor, FeatureMetadata


class EnhancedFeatures(BaseFeatureExtractor):
    """Extracts advanced momentum, volatility regime, and calendar features."""

    def __init__(
        self,
        rsi_periods: List[int] = [14],
        roc_periods: List[int] = [5, 10, 20],
    ) -> None:
        self.rsi_periods = rsi_periods
        self.roc_periods = roc_periods

    @property
    def metadata(self) -> FeatureMetadata:
        feature_names = (
            # Momentum divergence
            [f"rsi_divergence_{p}" for p in self.rsi_periods]
            + ["macd_hist_slope", "macd_hist_accel"]
            + [f"roc_{p}" for p in self.roc_periods]
            + ["momentum_score"]
            # Volatility regime
            + ["vol_regime_duration", "vol_of_vol_20", "vol_transition_prob"]
            # Calendar
            + ["day_of_week", "month_end_effect", "days_to_month_end"]
        )
        return FeatureMetadata(
            name="enhanced_features",
            feature_names=feature_names,
            description="Advanced momentum divergence, volatility regime persistence, and calendar effects",
            lookback_window=60,
        )

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        self.validate_input(df)
        res = pd.DataFrame(index=df.index)
        close = df["close"]

        # ── 1. Momentum Divergence Features ──────────────────────────────────

        # RSI divergence: difference between RSI slope and price slope
        for p in self.rsi_periods:
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=p, min_periods=p).mean()
            avg_loss = loss.rolling(window=p, min_periods=p).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))

            # RSI slope (5-day)
            rsi_slope = rsi.diff(5) / 5.0
            # Price slope (5-day, normalized)
            price_slope = close.pct_change(5) / 5.0
            # Divergence: RSI moving up while price moving down (or vice versa)
            res[f"rsi_divergence_{p}"] = rsi_slope - price_slope

        # MACD histogram slope and acceleration
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal

        hist_slope = hist.diff(3) / 3.0
        res["macd_hist_slope"] = hist_slope / close  # normalized
        res["macd_hist_accel"] = hist_slope.diff(3) / 3.0 / close  # second derivative

        # Rate of change across multiple horizons
        for p in self.roc_periods:
            res[f"roc_{p}"] = close.pct_change(p)

        # Composite momentum score: weighted average of normalized indicators.
        # Built from the configured periods so non-default rsi_periods/roc_periods
        # still produce a live (non-zero) score instead of silently zeroing.
        rsi_ref = f"rsi_divergence_{self.rsi_periods[0]}" if self.rsi_periods else "rsi_divergence_14"
        roc_ref = f"roc_{self.roc_periods[-1]}" if self.roc_periods else "roc_5"
        rsi_14 = res.get(rsi_ref, pd.Series(0.0, index=df.index))
        macd_s = res.get("macd_hist_slope", pd.Series(0.0, index=df.index))
        roc_5 = res.get(roc_ref, pd.Series(0.0, index=df.index))
        res["momentum_score"] = (
            0.3 * rsi_14.fillna(0)
            + 0.4 * macd_s.fillna(0)
            + 0.3 * roc_5.fillna(0)
        )

        # ── 2. Volatility Regime Features ────────────────────────────────────

        log_ret = np.log(close / close.shift(1))
        vol_20 = log_ret.rolling(20, min_periods=20).std()

        # Volatility-of-volatility (20-day rolling std of vol)
        res["vol_of_vol_20"] = vol_20.rolling(20, min_periods=20).std()

        # Volatility regime duration: consecutive days above/below median vol
        vol_median = vol_20.rolling(60, min_periods=20).median()
        above_median = (vol_20 > vol_median).astype(int)
        # Count consecutive True/False using groupby trick
        groups = (above_median != above_median.shift()).cumsum()
        vol_regime_duration = above_median.groupby(groups).cumsum()
        # Normalize by lookback
        res["vol_regime_duration"] = vol_regime_duration / 60.0

        # Volatility transition probability: likelihood of regime change
        # (high vol → low vol or vice versa) based on recent history
        vol_change = (vol_20.diff().abs() > vol_20.rolling(20, min_periods=5).std()).astype(int)
        res["vol_transition_prob"] = vol_change.rolling(20, min_periods=5).mean()

        # ── 3. Calendar Features ─────────────────────────────────────────────

        if hasattr(df.index, 'dayofweek'):
            dow = df.index.dayofweek
            # Cyclical encoding: sin/cos of day of week
            res["day_of_week"] = np.sin(2 * np.pi * dow / 5.0)  # 0-4 Mon-Fri

            if hasattr(df.index, 'day') and hasattr(df.index, 'days_in_month'):
                day_of_month = df.index.day
                days_in_month = np.asarray(df.index.days_in_month)
                # Fraction of the month remaining, using the actual month length
                res["days_to_month_end"] = (days_in_month - day_of_month) / days_in_month
                # Month-end effect: within the last 3 calendar days of the month
                res["month_end_effect"] = (days_in_month - day_of_month < 3).astype(float)
            else:
                res["days_to_month_end"] = 0.0
                res["month_end_effect"] = 0.0
        else:
            res["day_of_week"] = 0.0
            res["days_to_month_end"] = 0.0
            res["month_end_effect"] = 0.0

        return res
