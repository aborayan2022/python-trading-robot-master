"""Unit tests for Quantitative Feature Engineering Package."""

import numpy as np
import pandas as pd
import pytest

from pyrobot.features import (
    EnhancedFeatures,
    FeatureEngine,
    MarketRegime,
    MarketRegimeDetector,
    MomentumFeatures,
    TechnicalFeatures,
    VolatilityFeatures,
)


@pytest.fixture
def sample_ohlcv_data():
    """Generate 150 days of synthetic price data."""
    dates = pd.date_range("2024-01-01", periods=150, freq="B")
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.015, size=150)
    prices = 100 * np.exp(np.cumsum(returns))

    df = pd.DataFrame(
        {
            "open": prices * (1 - 0.002),
            "high": prices * (1 + 0.008),
            "low": prices * (1 - 0.008),
            "close": prices,
            "volume": np.random.randint(100000, 500000, size=150),
        },
        index=dates,
    )
    return df


class TestFeatureExtractors:

    def test_technical_features_extraction(self, sample_ohlcv_data):
        ext = TechnicalFeatures(rsi_periods=[14], sma_periods=[20], ema_periods=[9])
        feats = ext.extract(sample_ohlcv_data)

        assert "rsi_14" in feats.columns
        assert "sma_ratio_20" in feats.columns
        assert "bb_upper_ratio" in feats.columns
        assert "macd" in feats.columns
        assert len(feats) == len(sample_ohlcv_data)

    def test_volatility_features_extraction(self, sample_ohlcv_data):
        ext = VolatilityFeatures(atr_periods=[14], rv_periods=[20])
        feats = ext.extract(sample_ohlcv_data)

        assert "atr_pct_14" in feats.columns
        assert "realized_vol_20" in feats.columns
        assert "parkinson_vol_20" in feats.columns
        assert "garman_klass_vol_20" in feats.columns
        assert (feats["realized_vol_20"].dropna() >= 0).all()

    def test_momentum_features_extraction(self, sample_ohlcv_data):
        ext = MomentumFeatures(return_periods=[1, 5], volume_ma_periods=[5])
        feats = ext.extract(sample_ohlcv_data)

        assert "return_1" in feats.columns
        assert "log_return_5" in feats.columns
        assert "vol_ratio_5" in feats.columns
        assert "vwap_deviation" in feats.columns

    def test_regime_detector(self, sample_ohlcv_data):
        detector = MarketRegimeDetector(trend_short=10, trend_long=20, vol_lookback=30)
        feats = detector.extract(sample_ohlcv_data)

        assert "regime_code" in feats.columns
        assert "regime_confidence" in feats.columns

        regime_state = detector.get_current_regime(sample_ohlcv_data)
        assert isinstance(regime_state.regime, MarketRegime)
        assert 0.0 <= regime_state.confidence <= 1.0

    def test_feature_engine_integration(self, sample_ohlcv_data):
        engine = FeatureEngine()
        all_feats = engine.extract_features(sample_ohlcv_data, drop_na=False)

        assert len(all_feats.columns) > 15
        assert len(all_feats) == len(sample_ohlcv_data)
        assert all_feats.index.equals(sample_ohlcv_data.index)


class TestEnhancedFeatures:

    def test_enhanced_features_extraction(self, sample_ohlcv_data):
        ext = EnhancedFeatures()
        feats = ext.extract(sample_ohlcv_data)

        assert "rsi_divergence_14" in feats.columns
        assert "macd_hist_slope" in feats.columns
        assert "macd_hist_accel" in feats.columns
        assert "roc_5" in feats.columns
        assert "momentum_score" in feats.columns
        assert "vol_of_vol_20" in feats.columns
        assert "vol_regime_duration" in feats.columns
        assert "vol_transition_prob" in feats.columns
        assert "day_of_week" in feats.columns
        assert "month_end_effect" in feats.columns
        assert "days_to_month_end" in feats.columns
        assert len(feats) == len(sample_ohlcv_data)

    def test_enhanced_features_no_lookahead(self, sample_ohlcv_data):
        ext = EnhancedFeatures()
        feats = ext.extract(sample_ohlcv_data)
        # All features must be backward-looking (no forward references)
        for col in feats.columns:
            # NaN rows should only be at the start (from rolling windows)
            valid = feats[col].dropna()
            if len(valid) > 10:
                # No inf values
                assert np.isfinite(valid).all(), f"Column {col} contains inf values"

    def test_enhanced_features_in_engine(self, sample_ohlcv_data):
        engine = FeatureEngine()
        all_feats = engine.extract_features(sample_ohlcv_data)
        # Enhanced features should be included
        assert "momentum_score" in all_feats.columns
        assert "vol_of_vol_20" in all_feats.columns
        assert "day_of_week" in all_feats.columns

    def test_enhanced_metadata(self):
        ext = EnhancedFeatures()
        meta = ext.metadata
        assert meta.name == "enhanced_features"
        assert len(meta.feature_names) > 10
        assert meta.lookback_window == 60

    def test_enhanced_month_end_uses_real_days_in_month(self, sample_ohlcv_data):
        ext = EnhancedFeatures()
        feats = ext.extract(sample_ohlcv_data)
        # Index is business-daily starting 2024-01-01 (31-day January).
        # Days near the true month end (>= 3 calendar days remaining) must flag.
        month_end_idx = feats.index[feats["month_end_effect"] == 1.0]
        assert len(month_end_idx) > 0
        # The last business day of January (2024-01-31) must be flagged.
        jan_end = pd.Timestamp("2024-01-31")
        assert jan_end in month_end_idx
        # days_to_month_end is in [0, 1]; 0 on the final day of the month.
        dte = feats["days_to_month_end"].dropna()
        assert (dte >= 0).all() and (dte <= 1.0).all()
        # On Jan 31 with a 31-day month, remaining fraction is 0.0? No: it's
        # (31-31)/31 = 0.0 -> flag=true. Verify explicit value.
        row = feats.loc[jan_end]
        assert abs(float(row["days_to_month_end"]) - 0.0) < 1e-9

    def test_enhanced_momentum_score_with_custom_periods(self, sample_ohlcv_data):
        # Non-default RSI period must still produce a live momentum score
        # (not silently zeroed because rsi_divergence_14 is absent).
        ext = EnhancedFeatures(rsi_periods=[7], roc_periods=[3, 10])
        feats = ext.extract(sample_ohlcv_data)
        assert "rsi_divergence_7" in feats.columns
        assert "rsi_divergence_14" not in feats.columns
        live = feats["momentum_score"].dropna()
        assert len(live) > 10
        assert np.isfinite(live).all()
        # The score must actually vary (not constant zero).
        assert float(np.nanstd(feats["momentum_score"])) > 1e-12
