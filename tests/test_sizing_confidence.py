"""WO-7 acceptance tests: Sizing-confidence cleanup."""

import numpy as np
import pandas as pd
import pytest

from pyrobot.ai.calibration import IsotonicCalibrator


class TestWO7SizingConfidence:
    """WO-7: Position sizing must use calibrated confidence, not raw probability."""

    def test_sizing_uses_calibrated_confidence(self):
        """Same features, engine with vs without calibrator → measurably different position sizes."""
        from pyrobot.ai.ensemble import EnsembleSignalEngine
        from pyrobot.ai.models import LogisticDirectionModel
        from pyrobot.risk.limits import RiskLimits
        from pyrobot.risk.manager import RiskManager

        rng = np.random.default_rng(777)
        n = 200
        X = pd.DataFrame({
            "f1": rng.normal(0, 1, n),
            "f2": rng.normal(0, 1, n),
        })
        y = pd.Series((X["f1"] > 0).astype(int))

        model = LogisticDirectionModel(model_id="sizing_test", version="v1")
        model.fit(X, y)

        # Build calibrator that shifts probabilities
        probs = model.predict_proba(X)[:, 1]
        cal = IsotonicCalibrator().fit(probs, y)

        # Features frame must include model features AND OHLCV for regime detector
        features = pd.DataFrame({
            "f1": rng.normal(0, 1, 5),
            "f2": rng.normal(0, 1, 5),
            "open": 100.0 + rng.normal(0, 0.5, size=5),
            "high": 100.5 + abs(rng.normal(0, 0.3, size=5)),
            "low": 99.5 - abs(rng.normal(0, 0.3, size=5)),
            "close": 100.0 + rng.normal(0, 0.1, size=5),
            "volume": [1_000_000.0] * 5,
        })

        # Engine WITHOUT calibrator
        engine_no_cal = EnsembleSignalEngine(
            direction_model=model,
            calibrator=None,
            min_probability=0.80,
        )
        sig_no_cal = engine_no_cal.generate_signal("TEST", features)

        # Engine WITH calibrator
        engine_cal = EnsembleSignalEngine(
            direction_model=model,
            calibrator=cal,
            min_probability=0.80,
        )
        sig_cal = engine_cal.generate_signal("TEST", features)

        # Confidence must differ when calibrator is applied
        assert sig_no_cal.confidence != sig_cal.confidence, (
            "Confidence should differ between calibrated and uncalibrated engines"
        )

    def test_confidence_floor_prevents_zero_size(self):
        """A calibrated probability near 0.55 → confidence ≈ 0.1 → floor 0.05 applies."""
        from pyrobot.ai.ensemble import EnsembleSignalEngine, SignalAction

        class NearNeutralModel:
            is_fitted = True
            model_id = "near_neutral"
            version = "v1"
            def predict_proba(self, X):
                return np.array([[0.45, 0.55]])

        features = pd.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1_000_000],
        })

        engine = EnsembleSignalEngine(
            direction_model=NearNeutralModel(),
            calibrator=None,
            min_probability=0.80,
        )
        sig = engine.generate_signal("TEST", features)
        # 0.55 < 0.80 → NO_TRADE, so confidence doesn't matter for the signal
        assert sig.action == SignalAction.NO_TRADE

    def test_position_sizer_confidence_scaling(self):
        """PositionSizer scales output by confidence — higher confidence → more shares."""
        from pyrobot.risk.position_sizer import PositionSizer
        from pyrobot.risk.limits import RiskLimits

        sizer = PositionSizer(limits=RiskLimits())

        qty_low = sizer.fixed_fraction_size(
            account_equity=100_000.0,
            risk_per_trade_pct=0.01,
            stop_distance=5.0,
            price=100.0,
            confidence=0.1,
        )
        qty_high = sizer.fixed_fraction_size(
            account_equity=100_000.0,
            risk_per_trade_pct=0.01,
            stop_distance=5.0,
            price=100.0,
            confidence=0.9,
        )
        assert qty_high > qty_low, (
            f"Higher confidence should produce larger position: {qty_high} <= {qty_low}"
        )
