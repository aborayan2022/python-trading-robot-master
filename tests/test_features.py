"""Unit tests for Quantitative Feature Engineering Package."""

import pytest
import numpy as np
import pandas as pd

from pyrobot.features import (
    FeatureEngine,
    TechnicalFeatures,
    VolatilityFeatures,
    MomentumFeatures,
    MarketRegimeDetector,
    MarketRegime,
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
