"""Tests for production ML training gates and model governance."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from pyrobot.ai.calibration import IsotonicCalibrator
from pyrobot.ai.models import LogisticDirectionModel
from pyrobot.ai.registry import ModelMetadata, ModelRegistry, ModelStatus
from pyrobot.ai.training import (
    TrainingGateConfig,
    build_training_frame,
    train_direction_champion_candidate,
)
from pyrobot.data.base import Candle, DataFrequency, MarketDataProvider, Quote
from pyrobot.exceptions import ModelNotApprovedError


class _MemoryProvider(MarketDataProvider):
    def __init__(self, data):
        self.data = data

    def get_historical_candles(self, symbol, start, end, frequency=DataFrequency.MINUTE_1):
        return self.data[symbol]

    def get_latest_quote(self, symbol):
        return Quote(symbol, datetime.now(timezone.utc), 1.0, 1.1, 1.05)

    def get_quotes(self, symbols):
        return {s: self.get_latest_quote(s) for s in symbols}


def _candles(symbol="MSFT", n=900):
    start = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    for i in range(n):
        price *= 1.0 + (0.001 if i % 3 else -0.0002)
        ts = start + timedelta(days=i // 30, minutes=i % 30)
        rows.append(Candle(symbol, ts, price * 0.999, price * 1.002, price * 0.998, price, 100_000))
    return rows


def test_build_training_frame_downloads_multiple_symbols():
    provider = _MemoryProvider({"MSFT": _candles("MSFT", 20), "AAPL": _candles("AAPL", 20)})
    frame = build_training_frame(
        provider,
        ["MSFT", "AAPL"],
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert set(frame["symbol"]) == {"MSFT", "AAPL"}
    assert {"open", "high", "low", "close", "volume"}.issubset(frame.columns)


def test_registry_rejects_champion_without_artifact(tmp_path):
    registry = ModelRegistry(tmp_path)
    meta = ModelMetadata(
        model_id="bad",
        version="v1",
        model_type="logistic_direction",
        target_variable="dir_5",
        features=["x"],
        training_start="2026-01-01",
        training_end="2026-01-31",
        status=ModelStatus.CANDIDATE,
        oos_metrics={
            "oos_accuracy": 0.7,
            "buy_hold_accuracy": 0.5,
            "sma_accuracy": 0.51,
            "expected_calibration_error": 0.05,
            "oos_samples": 100,
        },
    )
    registry.register_model(meta)

    with pytest.raises(ModelNotApprovedError):
        registry.promote_to_champion("bad", "v1", approved_by="test")


def test_isotonic_calibrator_monotonic_and_reports_error():
    probs = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    labels = np.array([0, 0, 1, 1, 1])
    calibrator = IsotonicCalibrator().fit(probs, labels)
    transformed = calibrator.transform(probs)
    report = calibrator.report(probs, labels)

    assert np.all(np.diff(transformed) >= -1e-12)
    assert report["expected_calibration_error"] >= 0.0


def test_train_direction_candidate_registers_artifact(tmp_path):
    provider = _MemoryProvider({"MSFT": _candles("MSFT", 1300)})
    frame = build_training_frame(
        provider,
        ["MSFT"],
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    registry = ModelRegistry(tmp_path / "models")
    report = train_direction_champion_candidate(
        frame,
        registry,
        model_id="candidate",
        version="v1",
        gate=TrainingGateConfig(min_oos_samples=10, min_oos_accuracy_edge=-1.0, max_calibration_error=1.0),
        report_path=tmp_path / "report.json",
    )

    meta = registry.get_model("candidate", "v1")
    loaded = registry.load_model("candidate", "v1")
    assert isinstance(loaded, LogisticDirectionModel)
    assert meta.artifact_path
    assert report["walk_forward"]["n_oos_predictions"] > 0
    assert (tmp_path / "report.json").exists()


class TestWO3OOSECE:
    """WO-3: Calibration gate must use OOS predictions, not in-sample."""

    def test_ece_gate_uses_oos_predictions(self):
        """OOS probabilities are collected and available for calibration gating.

        The run_walk_forward function must populate oos_probabilities when
        proba_fn is provided, enabling downstream OOS ECE computation.
        """
        from pyrobot.backtesting.walk_forward import run_walk_forward

        rng = np.random.default_rng(55)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")

        X = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n)}, index=dates)
        true_y = (X["f1"] * 0.3 + X["f2"] * 0.2 + rng.normal(0, 0.5, size=n) > 0).astype(int)

        class SimpleModel:
            def fit(self, X_frame, y_series):
                self._p = float(y_series.mean())
            def predict(self, X_frame):
                return (np.ones(len(X_frame)) * self._p > 0.5).astype(int)
            def predict_proba(self, X_frame):
                p = np.full(len(X_frame), min(max(self._p, 0.01), 0.99))
                return np.column_stack([1 - p, p])

        result = run_walk_forward(
            X, true_y,
            model_factory=SimpleModel,
            train_fn=lambda m, x, y: m.fit(x, y),
            predict_fn=lambda m, x: m.predict(x),
            metric_fn=lambda y, p: float(np.mean(y.to_numpy() == np.asarray(p, dtype=int))),
            n_splits=3,
            train_period_days=60,
            test_period_days=20,
            embargo_days=1,
            expanding=True,
            purge_bars=5,
            proba_fn=lambda m, x: m.predict_proba(x),
        )

        # OOS probabilities must be collected
        assert len(result.oos_probabilities) > 0
        assert len(result.oos_probabilities) == len(result.oos_labels)

        # Fit calibrator on OOS and verify ECE is computable
        oos_cal = IsotonicCalibrator().fit(result.oos_probabilities, result.oos_labels)
        oos_report = oos_cal.report(result.oos_probabilities, result.oos_labels)
        assert "expected_calibration_error" in oos_report
        assert oos_report["expected_calibration_error"] >= 0.0

        # Without proba_fn, oos_probabilities must be empty
        result_no_proba = run_walk_forward(
            X, true_y,
            model_factory=SimpleModel,
            train_fn=lambda m, x, y: m.fit(x, y),
            predict_fn=lambda m, x: m.predict(x),
            metric_fn=lambda y, p: float(np.mean(y.to_numpy() == np.asarray(p, dtype=int))),
            n_splits=3,
            train_period_days=60,
            test_period_days=20,
            embargo_days=1,
            expanding=True,
            purge_bars=5,
        )
        assert len(result_no_proba.oos_probabilities) == 0

    def test_gate_rejects_overconfident_model(self):
        """An overconfident model should fail the OOS calibration gate.

        Under in-sample gating it would pass (ECE ≈ 0 after isotonic fit),
        but under OOS gating the material miscalibration is detected.
        """
        from pyrobot.backtesting.walk_forward import run_walk_forward

        rng = np.random.default_rng(66)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")

        X = pd.DataFrame({"f1": rng.normal(size=n)}, index=dates)
        true_y = pd.Series((X["f1"] > 0).astype(int), index=dates)

        class OverconfidentModel:
            def fit(self, X_frame, y_series):
                pass
            def predict(self, X_frame):
                return np.ones(len(X_frame), dtype=int)
            def predict_proba(self, X_frame):
                p = np.full(len(X_frame), 0.95)
                return np.column_stack([1 - p, p])

        result = run_walk_forward(
            X, true_y,
            model_factory=OverconfidentModel,
            train_fn=lambda m, x, y: m.fit(x, y),
            predict_fn=lambda m, x: m.predict(x),
            metric_fn=lambda y, p: float(np.mean(y.to_numpy() == np.asarray(p, dtype=int))),
            n_splits=3,
            train_period_days=60,
            test_period_days=20,
            embargo_days=1,
            expanding=True,
            purge_bars=5,
            proba_fn=lambda m, x: m.predict_proba(x),
        )

        # Fit calibrator on OOS probabilities
        oos_cal = IsotonicCalibrator().fit(result.oos_probabilities, result.oos_labels)
        oos_report = oos_cal.report(result.oos_probabilities, result.oos_labels)

        # OOS ECE should be material (model is overconfident and wrong OOS)
        # The gate with max_calibration_error=0.15 should reject this
        gate = TrainingGateConfig(max_calibration_error=0.15)
        assert oos_report["expected_calibration_error"] > gate.max_calibration_error
