"""Unit tests for the AI & Machine Learning Quantitative Platform."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pyrobot.ai import (
    ArtifactIntegrityError,
    DriftDetector,
    EnsembleSignalEngine,
    GBDTDirectionClassifier,
    LabelBuilder,
    LexiconSentimentEngine,
    LLMContextEngine,
    LogisticDirectionModel,
    ModelMetadata,
    ModelRegistry,
    ModelStatus,
    NewsEventType,
    VolatilityForecaster,
)
from pyrobot.models.signal import SignalAction


class TestModelRegistry:
    def test_champion_challenger_lifecycle(self) -> None:
        rng = np.random.default_rng(55)
        X = pd.DataFrame({
            "rsi_14": rng.uniform(20, 80, 120),
            "vol_ratio": rng.normal(0, 1, 120),
            "momentum": rng.normal(0, 1, 120),
        })
        y = pd.Series(((X["rsi_14"] - 50) + X["vol_ratio"] + X["momentum"] > 0).astype(int))
        governance_metrics = {
            "oos_accuracy": 0.70,
            "buy_hold_accuracy": 0.55,
            "sma_accuracy": 0.56,
            "expected_calibration_error": 0.05,
            "oos_samples": 100,
            # WO-4: Economic metrics required for champion promotion
            "net_pnl_after_costs": 5000.0,
            "sharpe": 1.5,
            "max_drawdown": -0.05,
            "profit_factor": 1.8,
            "n_trades": 30,
            "ev_per_trade": 150.0,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)

            rejected = ModelMetadata(
                model_id="xgb_direction",
                version="v0.1",
                model_type=LogisticDirectionModel.model_type,
                target_variable="return_5d_sign",
                features=["rsi_14", "vol_ratio"],
                training_start="2024-01-01",
                training_end="2025-01-01",
                status=ModelStatus.CANDIDATE,
            )
            registry.register_model(rejected)
            from pyrobot.exceptions import ModelNotApprovedError

            with pytest.raises(ModelNotApprovedError):
                registry.promote_to_champion("xgb_direction", "v0.1", approved_by="RiskCommittee")

            model_v1 = LogisticDirectionModel(model_id="xgb_direction", version="v1.0").fit(
                X[["rsi_14", "vol_ratio"]], y
            )
            m1 = ModelMetadata(
                model_id="xgb_direction",
                version="v1.0",
                model_type=LogisticDirectionModel.model_type,
                target_variable="return_5d_sign",
                features=["rsi_14", "vol_ratio"],
                training_start="2024-01-01",
                training_end="2025-01-01",
                status=ModelStatus.CANDIDATE,
                oos_metrics=governance_metrics,
            )
            registry.register_model(m1, model=model_v1)

            loaded = registry.get_model("xgb_direction", "v1.0")
            assert loaded.model_id == "xgb_direction"
            assert loaded.status == ModelStatus.CANDIDATE

            champ = registry.promote_to_champion("xgb_direction", "v1.0", approved_by="RiskCommittee")
            assert champ.status == ModelStatus.CHAMPION
            assert registry.get_champion().version == "v1.0"

            model_v2 = LogisticDirectionModel(model_id="xgb_direction", version="v2.0").fit(
                X[["rsi_14", "vol_ratio", "momentum"]], y
            )
            m2 = ModelMetadata(
                model_id="xgb_direction",
                version="v2.0",
                model_type=LogisticDirectionModel.model_type,
                target_variable="return_5d_sign",
                features=["rsi_14", "vol_ratio", "momentum"],
                training_start="2024-01-01",
                training_end="2025-06-01",
                oos_metrics=governance_metrics,
            )
            registry.register_model(m2, model=model_v2)
            registry.promote_to_challenger("xgb_direction", "v2.0")

            challengers = registry.get_challengers()
            assert len(challengers) == 1
            assert challengers[0].version == "v2.0"

            registry.promote_to_champion("xgb_direction", "v2.0", approved_by="RiskCommittee")
            assert registry.get_champion().version == "v2.0"
            assert registry.get_model("xgb_direction", "v1.0").status == ModelStatus.ARCHIVED

    def test_registry_artifact_round_trip(self) -> None:
        """register_model(model=...) persists weights; load_model restores them."""
        rng = np.random.default_rng(5)
        n = 120
        X = pd.DataFrame({
            "rsi_14": rng.uniform(20, 80, n),
            "momentum_10": rng.normal(0, 1, n),
        })
        logits = 0.06 * (X["rsi_14"] - 50) + 0.8 * X["momentum_10"]
        y = pd.Series((logits > 0).astype(int))

        model = LogisticDirectionModel(model_id="dir_model", version="v1.0")
        model.fit(X, y)

        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)
            meta = ModelMetadata(
                model_id="dir_model",
                version="v1.0",
                model_type=LogisticDirectionModel.model_type,
                target_variable="dir_5",
                features=list(X.columns),
                training_start="2024-01-01",
                training_end="2025-01-01",
            )
            registry.register_model(meta, model=model)
            assert meta.artifact_path is not None
            assert meta.artifact_sha256 is not None

            restored = registry.load_model("dir_model", "v1.0")
            assert isinstance(restored, LogisticDirectionModel)
            assert restored.is_fitted
            # Same weights -> identical predictions on fresh rows
            np.testing.assert_allclose(
                restored.predict_proba(X.iloc[:10]),
                model.predict_proba(X.iloc[:10]),
            )

    def test_registry_rejects_tampered_artifact(self) -> None:
        rng = np.random.default_rng(9)
        X = pd.DataFrame({"f": rng.normal(size=60)})
        y = pd.Series((X["f"] > 0).astype(int))
        model = LogisticDirectionModel(model_id="tamper_test", version="v1.0").fit(X, y)

        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)
            meta = ModelMetadata(
                model_id="tamper_test",
                version="v1.0",
                model_type=LogisticDirectionModel.model_type,
                target_variable="dir_1",
                features=["f"],
                training_start="2024-01-01",
                training_end="2025-01-01",
            )
            registry.register_model(meta, model=model)

            # Corrupt the artifact bytes -> checksum must fail on load
            with open(meta.artifact_path, "ab") as f:
                f.write(b"tampered")
            with pytest.raises(ArtifactIntegrityError):
                registry.load_model("tamper_test", "v1.0")

    def test_registry_rejects_unfitted_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)
            meta = ModelMetadata(
                model_id="unfitted", version="v1.0",
                model_type=LogisticDirectionModel.model_type,
                target_variable="dir_1", features=["f"],
                training_start="2024-01-01", training_end="2025-01-01",
            )
            with pytest.raises(ValueError):
                registry.register_model(meta, model=LogisticDirectionModel())


class TestQuantModels:
    def test_logistic_direction_model_learns_separable_target(self) -> None:
        """Real variability + truly separable target: accuracy must be high."""
        rng = np.random.default_rng(42)
        n = 400
        X = pd.DataFrame({
            "rsi_14": rng.uniform(20, 80, n),
            "momentum_10": rng.normal(0, 1, n),
        })
        logits = 0.08 * (X["rsi_14"] - 50) + 1.2 * X["momentum_10"]
        y = pd.Series((logits > 0).astype(int))

        clf = LogisticDirectionModel(model_id="test_clf", n_iterations=4000, learning_rate=0.5)
        clf.fit(X, y)

        assert clf.is_fitted
        assert clf.n_iter_run <= 4000
        preds = clf.predict(X)
        accuracy = float((preds == y.to_numpy()).mean())
        assert accuracy > 0.9  # linearly separable — must be near-perfect
        assert len(clf.feature_importances_) == 2
        probs = clf.predict_proba(X.iloc[:5])
        assert probs.shape == (5, 2)
        assert np.allclose(probs[:, 0] + probs[:, 1], 1.0)

    def test_gbdt_alias_is_logistic_model(self) -> None:
        """The legacy name must be an alias of the honestly-named model."""
        assert GBDTDirectionClassifier is LogisticDirectionModel

    def test_convergence_early_stop(self) -> None:
        rng = np.random.default_rng(3)
        X = pd.DataFrame({"f": rng.normal(size=200)})
        y = pd.Series((X["f"] > 0).astype(int))
        clf = LogisticDirectionModel(n_iterations=100000, tol=1e-4, learning_rate=0.5)
        clf.fit(X, y)
        assert clf.n_iter_run < 10000  # converged well before the cap

    def test_model_save_load_round_trip(self, tmp_path) -> None:
        rng = np.random.default_rng(7)
        X = pd.DataFrame({"a": rng.normal(size=100), "b": rng.normal(size=100)})
        y = pd.Series((X["a"] + 0.5 * X["b"] > 0).astype(int))
        model = LogisticDirectionModel(model_id="rt", version="v9").fit(X, y)
        path = tmp_path / "rt.npz"
        model.save(path)

        restored = LogisticDirectionModel.load(path)
        assert restored.model_id == "rt"
        assert restored.is_fitted
        np.testing.assert_allclose(
            restored.predict_proba(X), model.predict_proba(X), atol=1e-12
        )

        vol = VolatilityForecaster(model_id="v").fit(X, pd.Series(0.02 + 0.01 * X["a"]))
        vol_path = tmp_path / "vol.npz"
        vol.save(vol_path)
        vol_back = VolatilityForecaster.load(vol_path)
        np.testing.assert_allclose(vol_back.predict(X), vol.predict(X), atol=1e-12)

    def test_volatility_forecaster(self) -> None:
        rng = np.random.default_rng(42)
        n = 80
        X = pd.DataFrame({
            "hist_vol_20": rng.uniform(0.01, 0.05, n),
            "atr_ratio": rng.uniform(0.8, 1.5, n),
        })
        y = pd.Series(0.8 * X["hist_vol_20"] + 0.01 * X["atr_ratio"])

        reg = VolatilityForecaster(model_id="test_vol")
        reg.fit(X, y)

        assert reg.is_fitted
        preds = reg.predict(X.iloc[:5])
        assert len(preds) == 5
        assert (preds > 0).all()


def _trend_features_df(periods: int = 60) -> pd.DataFrame:
    """Rising OHLCV frame with varying (non-constant) feature columns."""
    dates = pd.date_range("2026-01-01", periods=periods, freq="D", tz="UTC")
    close = np.linspace(100, 160, periods)
    return pd.DataFrame({
        "open": close - 1.0,
        "high": close + 2.0,
        "low": close - 2.0,
        "close": close,
        "volume": np.linspace(10000, 20000, periods),
        "rsi_14": np.linspace(45, 75, periods),
        "momentum_10": np.linspace(0.001, 0.05, periods),
    }, index=dates)


class _ConstantModel:
    """Test double standing in for a fitted direction model."""

    model_type = "logistic_direction"

    def __init__(self, prob_up: float) -> None:
        self.prob_up = prob_up
        self.is_fitted = True
        self.model_id = "mock_dir"
        self.version = "v1.0"

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        p = self.prob_up
        return np.array([[1.0 - p, p]] * len(X))


class TestEnsembleSignalEngine:
    def test_high_prob_bullish_in_bull_regime_buys(self) -> None:
        df = _trend_features_df()
        engine = EnsembleSignalEngine(direction_model=_ConstantModel(0.92))  # type: ignore[arg-type]
        signal = engine.generate_signal(symbol="AAPL", features_df=df)
        assert signal.action == SignalAction.BUY
        assert signal.probability == pytest.approx(0.92)
        assert signal.confidence == pytest.approx(0.84, abs=0.01)

    def test_high_prob_bearish_in_bull_regime_does_not_buy(self) -> None:
        df = _trend_features_df()  # BULL regime
        engine = EnsembleSignalEngine(direction_model=_ConstantModel(0.08))  # type: ignore[arg-type]
        signal = engine.generate_signal(symbol="AAPL", features_df=df)
        # Bearish entry requires BEAR/HIGH_VOL regime — BULL regime blocks shorts here
        assert signal.action != SignalAction.BUY
        assert signal.action != SignalAction.SELL_SHORT

    def test_crisis_regime_blocks_all_trades(self) -> None:
        # Quiet market then violent crash: max vol percentile + steep negative
        # trend at the final bar triggers the CRISIS regime.
        quiet = 100 + 0.05 * np.sin(np.arange(90))
        closes = list(quiet)
        price = 100.0
        for i in range(16):
            price *= 1.18 if i % 2 == 0 else 0.80
            closes.append(price)
        closes.append(price * 0.65)
        closes_arr = np.array(closes)
        df = pd.DataFrame({
            "open": closes_arr, "high": closes_arr * 1.01,
            "low": closes_arr * 0.99, "close": closes_arr,
            "volume": [10000] * len(closes_arr),
        }, index=pd.date_range("2026-01-01", periods=len(closes_arr), freq="D", tz="UTC"))
        engine = EnsembleSignalEngine(direction_model=_ConstantModel(0.99))  # type: ignore[arg-type]
        signal = engine.generate_signal(symbol="AAPL", features_df=df)
        assert signal.action == SignalAction.NO_TRADE
        assert "CRISIS" in (signal.reason or "")

    def test_exit_signals_for_held_positions(self) -> None:
        df = _trend_features_df()

        # Long held, model turned bearish -> exit long
        engine_long = EnsembleSignalEngine(direction_model=_ConstantModel(0.30))  # type: ignore[arg-type]
        long_exit = engine_long.generate_signal(
            symbol="AAPL", features_df=df, position_state={"AAPL": 100}
        )
        assert long_exit.action == SignalAction.SELL

        # Short held, model turned bullish -> cover short
        engine_short = EnsembleSignalEngine(direction_model=_ConstantModel(0.70))  # type: ignore[arg-type]
        short_cover = engine_short.generate_signal(
            symbol="AAPL", features_df=df, position_state={"AAPL": -100}
        )
        assert short_cover.action == SignalAction.BUY_TO_COVER

        # No position, middling probability -> no entry, no exit
        flat = engine_long.generate_signal(symbol="AAPL", features_df=df, position_state={})
        assert flat.action == SignalAction.NO_TRADE  # 0.30 not <= 0.20, no entry

    def test_threshold_below_half_rejected(self) -> None:
        with pytest.raises(ValueError):
            EnsembleSignalEngine(min_probability=0.4)
        with pytest.raises(ValueError):
            EnsembleSignalEngine(exit_probability=0.7)

    def test_registry_champion_loading(self) -> None:
        """Engine with no injected models loads the registry champion lazily."""
        rng = np.random.default_rng(5)
        X = pd.DataFrame({
            "rsi_14": rng.uniform(20, 80, 300),
            "momentum_10": rng.normal(0, 1, 300),
        })
        y = pd.Series(((0.08 * (X["rsi_14"] - 50) + 1.0 * X["momentum_10"]) > 0).astype(int))
        model = LogisticDirectionModel(model_id="champ", version="v1.0").fit(X, y)

        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)
            meta = ModelMetadata(
                model_id="champ", version="v1.0",
                model_type=LogisticDirectionModel.model_type,
                target_variable="dir_1", features=list(X.columns),
                training_start="2024-01-01", training_end="2025-01-01",
                oos_metrics={
                    "oos_accuracy": 0.80,
                    "buy_hold_accuracy": 0.55,
                    "sma_accuracy": 0.56,
                    "expected_calibration_error": 0.05,
                    "oos_samples": 120,
                    "net_pnl_after_costs": 5000.0,
                    "sharpe": 1.5,
                    "max_drawdown": -0.05,
                    "profit_factor": 1.8,
                    "n_trades": 30,
                    "ev_per_trade": 150.0,
                },
            )
            registry.register_model(meta, model=model)
            registry.promote_to_champion("champ", "v1.0", approved_by="tester")

            engine = EnsembleSignalEngine(registry=registry)
            assert engine.direction_model is None  # lazy
            # Full OHLCV frame (regime detector needs OHLC) incl. model features
            df = _trend_features_df()
            signal = engine.generate_signal(symbol="AAPL", features_df=df)
            assert engine.direction_model is not None
            assert signal.model_id == "champ:v1.0"


class TestDriftDetector:
    def test_psi_and_drift_detection(self) -> None:
        np.random.seed(42)
        baseline = pd.DataFrame({"feature_a": np.random.normal(0, 1, 500)})
        current_stable = pd.DataFrame({"feature_a": np.random.normal(0, 1, 500)})

        detector = DriftDetector()
        report_stable = detector.evaluate_drift(baseline, current_stable)
        assert report_stable.is_drift_detected is False
        assert report_stable.max_psi < 0.10

        current_shifted = pd.DataFrame({"feature_a": np.random.normal(3.0, 1, 500)})
        report_shifted = detector.evaluate_drift(baseline, current_shifted)
        assert report_shifted.is_drift_detected is True
        assert report_shifted.max_psi >= 0.25
        assert "feature_a" in report_shifted.flagged_features


class TestLabelBuilder:
    def _toy_frame(self) -> pd.DataFrame:
        # closes: 100, 110, 99, 105 -> fwd rets at h=1: 10%, -10%, ~6.06%, NaN
        return pd.DataFrame({
            "open": [100.0, 109.0, 100.0, 104.0],
            "high": [101.0, 111.0, 101.0, 106.0],
            "low": [99.0, 98.0, 98.0, 103.0],
            "close": [100.0, 110.0, 99.0, 105.0],
        }, index=pd.date_range("2026-01-01", periods=4, freq="D"))

    def test_forward_returns_hand_computed(self) -> None:
        out = LabelBuilder.forward_returns(self._toy_frame(), horizons=(1,))
        expected = [110 / 100 - 1, 99 / 110 - 1, 105 / 99 - 1, np.nan]
        np.testing.assert_allclose(out["fwd_ret_1"].to_numpy(), expected, rtol=1e-6)

    def test_direction_labels_and_drop_unlabeled(self) -> None:
        builder = LabelBuilder()
        labels = builder.direction_labels(self._toy_frame(), horizon=1, threshold=0.0)
        np.testing.assert_array_equal(labels.to_numpy()[:3], [1.0, 0.0, 1.0])
        assert np.isnan(labels.iloc[-1])

        dropped = builder.drop_unlabeled(labels)
        assert len(dropped) == 3

        # Multi-symbol frames group per symbol
        frame_multi = pd.concat(
            [self._toy_frame().assign(symbol=s).set_index("symbol", append=True)
             for s in ("A", "B")],
        ).reorder_levels(["symbol", None])
        labels_multi = builder.direction_labels(frame_multi, horizon=1)
        dropped_multi = builder.drop_unlabeled(labels_multi)
        assert len(dropped_multi) == 6  # 3 labeled rows per symbol

    def test_triple_barrier_monotonic_rise_is_profit(self) -> None:
        # Steady +1%/bar with tiny ranges: profit barrier hits, stop never does.
        n = 60
        close = 100.0 * (1.01 ** np.arange(n))
        frame = pd.DataFrame({
            "open": close / 1.01,
            "high": close * 1.001,
            "low": close / 1.001,
            "close": close,
        }, index=pd.date_range("2026-01-01", periods=n, freq="D"))
        labels = LabelBuilder().triple_barrier_labels(
            frame, horizon=10, up_mult=2.0, down_mult=1.0, atr_period=14
        )
        labeled = LabelBuilder.drop_unlabeled(labels)
        # Every labeled row should be +1 (profit barrier) on a monotonic rise
        assert (labeled == 1.0).all()

    def test_triple_barrier_crash_is_stop(self) -> None:
        n = 60
        close = np.concatenate([np.full(40, 100.0), np.linspace(100.0, 50.0, 20)])
        frame = pd.DataFrame({
            "open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
        }, index=pd.date_range("2026-01-01", periods=n, freq="D"))
        labels = LabelBuilder().triple_barrier_labels(
            frame, horizon=10, up_mult=1.0, down_mult=1.0, atr_period=14
        )
        LabelBuilder.drop_unlabeled(labels)
        # During the crash segment the stop barrier must dominate
        crash_labels = labels.iloc[45:50].dropna()
        assert (crash_labels == -1.0).all()


class TestLexiconSentimentEngine:
    def test_headline_analysis(self) -> None:
        engine = LexiconSentimentEngine()
        res_bull = engine.analyze_headline(
            symbol="NVDA",
            headline="NVIDIA surges as AI chip revenue beats record high estimates",
        )
        assert res_bull.symbol == "NVDA"
        assert res_bull.sentiment_score > 0.0
        assert res_bull.event_type == NewsEventType.EARNINGS_RELEASE

        res_bear = engine.analyze_headline(
            symbol="XYZ",
            headline="Regulators launch probe into accounting fraud after quarterly loss plunge",
        )
        assert res_bear.sentiment_score < 0.0
        assert res_bear.event_type == NewsEventType.REGULATORY_LEGAL

    def test_legacy_alias(self) -> None:
        assert LLMContextEngine is LexiconSentimentEngine

    def test_trade_explainability(self) -> None:
        engine = LexiconSentimentEngine()
        explanation = engine.explain_trade_decision(
            symbol="AAPL",
            signal_reason="Bullish Momentum in Trend",
            regime_name="BULL",
            confidence=0.85,
            risk_decision_reason="Passed all exposure and drawdown gates",
            approved=True,
        )
        assert "EXECUTED" in explanation
        assert "AAPL" in explanation
        assert "BULL" in explanation


class TestWO1CalibratorPersistence:
    """WO-1: Calibrator must be persisted, loaded, and applied at inference."""

    def test_calibrator_save_load_round_trip(self, tmp_path):
        """save() + load() produces identical transform output."""
        from pyrobot.ai.calibration import IsotonicCalibrator

        rng = np.random.default_rng(42)
        probs = rng.uniform(0.1, 0.9, size=200)
        labels = (probs + rng.normal(0, 0.1, size=200) > 0.5).astype(int)

        cal = IsotonicCalibrator().fit(probs, labels)
        original = cal.transform(probs)

        path = tmp_path / "calib.npz"
        cal.save(path)
        loaded = IsotonicCalibrator.load(path)

        assert loaded.is_fitted
        np.testing.assert_array_equal(original, loaded.transform(probs))

    def test_calibrator_registry_round_trip(self, tmp_path):
        """Register model + calibrator, load in a fresh engine, assert identical."""
        from pyrobot.ai.calibration import IsotonicCalibrator

        rng = np.random.default_rng(43)
        X = pd.DataFrame({"f1": rng.normal(size=100), "f2": rng.normal(size=100)})
        y = pd.Series((X["f1"] > 0).astype(int))

        model = LogisticDirectionModel(model_id="test_model", version="v1")
        model.fit(X, y)

        probs = model.predict_proba(X)[:, 1]
        cal = IsotonicCalibrator().fit(probs, y)

        registry = ModelRegistry(tmp_path / "models")
        meta = ModelMetadata(
            model_id="test_model",
            version="v1",
            model_type="logistic_direction",
            target_variable="dir_5",
            features=["f1", "f2"],
            training_start="2026-01-01",
            training_end="2026-01-31",
        )
        registry.register_model(meta, model=model, calibrator=cal)

        # Load calibrator from registry
        loaded_cal = registry.load_calibrator("test_model", "v1")
        assert loaded_cal is not None
        assert loaded_cal.is_fitted

        # Transform must be identical
        original_transform = cal.transform(np.array([0.3, 0.7]))
        loaded_transform = loaded_cal.transform(np.array([0.3, 0.7]))
        np.testing.assert_array_almost_equal(original_transform, loaded_transform)

    def test_calibrator_tamper_detected(self, tmp_path):
        """Modify one byte of .calib.npz → ArtifactIntegrityError."""
        from pyrobot.ai.calibration import IsotonicCalibrator
        from pyrobot.ai.registry import ArtifactIntegrityError

        rng = np.random.default_rng(44)
        probs = rng.uniform(0.1, 0.9, size=50)
        labels = (probs > 0.5).astype(int)

        cal = IsotonicCalibrator().fit(probs, labels)
        model = LogisticDirectionModel(model_id="tamper_test", version="v1")
        X = pd.DataFrame({"f1": rng.normal(size=50)})
        y = pd.Series(labels)
        model.fit(X, y)

        registry = ModelRegistry(tmp_path / "models")
        meta = ModelMetadata(
            model_id="tamper_test",
            version="v1",
            model_type="logistic_direction",
            target_variable="dir_5",
            features=["f1"],
            training_start="2026-01-01",
            training_end="2026-01-31",
        )
        registry.register_model(meta, model=model, calibrator=cal)

        # Tamper with the calibrator file
        calib_path = Path(meta.calibration_path)
        data = bytearray(calib_path.read_bytes())
        data[10] ^= 0xFF  # flip bits
        calib_path.write_bytes(bytes(data))

        with pytest.raises(ArtifactIntegrityError):
            registry.load_calibrator("tamper_test", "v1")

    def test_threshold_sees_calibrated_probability(self):
        """Raw p=0.82 but calibrated p=0.74 → NO_TRADE (below 0.80 threshold)."""
        from pyrobot.ai.calibration import IsotonicCalibrator

        # Build a calibrator that shifts 0.82 down to 0.74
        # Train on data where 0.80-0.85 probabilities correspond to ~0.74 true rate
        train_probs = np.array([0.70, 0.75, 0.80, 0.82, 0.85, 0.90])
        train_labels = np.array([0, 0, 1, 1, 0, 1])
        cal = IsotonicCalibrator().fit(train_probs, train_labels)

        # Raw 0.82 should be above threshold
        assert 0.82 >= 0.80

        # But calibrated 0.74 should be below threshold
        calibrated = cal.transform(np.array([0.82]))[0]
        assert calibrated < 0.80

        class MockModel:
            is_fitted = True
            model_id = "mock"
            version = "v1"
            def predict_proba(self, X):
                return np.array([[0.18, 0.82]])

        # Features must include OHLCV columns for regime detector
        features = pd.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000000],
        })

        # Without calibrator: would be BUY (0.82 >= 0.80)
        engine_no_cal = EnsembleSignalEngine(
            direction_model=MockModel(),
            calibrator=None,
            min_probability=0.80,
        )
        sig_no_cal = engine_no_cal.generate_signal("TEST", features)
        assert sig_no_cal.action == SignalAction.BUY

        # With calibrator: should be NO_TRADE (calibrated 0.74 < 0.80)
        engine_cal = EnsembleSignalEngine(
            direction_model=MockModel(),
            calibrator=cal,
            min_probability=0.80,
        )
        sig_cal = engine_cal.generate_signal("TEST", features)
        assert sig_cal.action == SignalAction.NO_TRADE


class TestOptionalLightGBMDirectionModel:
    """Tests for LightGBM model persistence and integration."""

    def test_lightgbm_save_load_round_trip(self, tmp_path) -> None:
        """LightGBM model must survive save→load with identical predictions."""
        lightgbm = pytest.importorskip("lightgbm")
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        rng = np.random.default_rng(42)
        X = pd.DataFrame({"a": rng.normal(size=100), "b": rng.normal(size=100)})
        y = pd.Series((X["a"] + 0.5 * X["b"] > 0).astype(int))
        model = OptionalLightGBMDirectionModel(model_id="lgbm_rt", version="v1").fit(X, y)
        path = tmp_path / "lgbm_model.joblib"
        model.save(path)

        restored = OptionalLightGBMDirectionModel.load(path)
        assert restored.model_id == "lgbm_rt"
        assert restored.is_fitted
        np.testing.assert_allclose(
            restored.predict_proba(X), model.predict_proba(X), atol=1e-10
        )

    def test_lightgbm_model_type_registered(self) -> None:
        """LightGBM model_type must be resolvable via model_class_for_type."""
        from pyrobot.ai.models import model_class_for_type
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        cls = model_class_for_type("lightgbm_direction")
        assert cls is OptionalLightGBMDirectionModel

    def test_lightgbm_predict_proba_shape(self) -> None:
        """LightGBM predict_proba must return [n_samples, 2] with P(down), P(up)."""
        lightgbm = pytest.importorskip("lightgbm")
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        rng = np.random.default_rng(99)
        X = pd.DataFrame({"x1": rng.normal(size=80), "x2": rng.normal(size=80)})
        y = pd.Series((X["x1"] > 0).astype(int))
        model = OptionalLightGBMDirectionModel(model_id="shape_test").fit(X, y)
        proba = model.predict_proba(X)
        assert proba.shape == (80, 2)
        assert np.all(proba >= 0) and np.all(proba <= 1)
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-10)

    def test_lightgbm_save_unfitted_raises(self, tmp_path) -> None:
        """Saving an unfitted LightGBM model must raise RuntimeError."""
        lightgbm = pytest.importorskip("lightgbm")
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        model = OptionalLightGBMDirectionModel(model_id="unfitted")
        with pytest.raises(RuntimeError, match="fitted"):
            model.save(tmp_path / "bad.joblib")

    def test_lightgbm_load_missing_file(self, tmp_path) -> None:
        """Loading from a nonexistent path must raise FileNotFoundError."""
        lightgbm = pytest.importorskip("lightgbm")
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        with pytest.raises(FileNotFoundError):
            OptionalLightGBMDirectionModel.load(tmp_path / "nonexistent.joblib")

    def test_lightgbm_registry_round_trip(self, tmp_path) -> None:
        """LightGBM model must be registerable and loadable via ModelRegistry."""
        lightgbm = pytest.importorskip("lightgbm")
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        rng = np.random.default_rng(77)
        X = pd.DataFrame({"f1": rng.normal(size=100), "f2": rng.normal(size=100)})
        y = pd.Series((X["f1"] > 0).astype(int))
        model = OptionalLightGBMDirectionModel(model_id="lgbm_reg", version="v1").fit(X, y)

        registry = ModelRegistry(registry_dir=tmp_path)
        meta = ModelMetadata(
            model_id="lgbm_reg",
            version="v1",
            model_type="lightgbm_direction",
            target_variable="dir_5",
            features=["f1", "f2"],
            training_start="2026-01-01",
            training_end="2026-08-30",
        )
        registry.register_model(meta, model=model)
        loaded = registry.load_model("lgbm_reg", "v1")
        assert loaded.model_id == "lgbm_reg"
        assert loaded.is_fitted
        np.testing.assert_allclose(
            loaded.predict_proba(X), model.predict_proba(X), atol=1e-10
        )

    def test_lightgbm_registry_tamper_detected(self, tmp_path) -> None:
        """A corrupted LightGBM artifact must fail ModelRegistry's SHA-256 check."""
        lightgbm = pytest.importorskip("lightgbm")
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        rng = np.random.default_rng(12)
        X = pd.DataFrame({"f1": rng.normal(size=100), "f2": rng.normal(size=100)})
        y = pd.Series((X["f1"] > 0).astype(int))
        model = OptionalLightGBMDirectionModel(model_id="lgbm_tamper").fit(X, y)

        registry = ModelRegistry(registry_dir=tmp_path)
        meta = ModelMetadata(
            model_id="lgbm_tamper",
            version="v1",
            model_type="lightgbm_direction",
            target_variable="dir_5",
            features=["f1", "f2"],
            training_start="2026-01-01",
            training_end="2026-08-30",
        )
        registry.register_model(meta, model=model)
        artifact = next(tmp_path.glob("lgbm_tamper*.npz"))
        # Corrupt a byte in the middle of the authoritative artifact
        raw = bytearray(artifact.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        artifact.write_bytes(bytes(raw))
        with pytest.raises(ArtifactIntegrityError, match="checksum mismatch"):
            registry.load_model("lgbm_tamper", "v1")

    def test_lightgbm_self_contained_metadata(self, tmp_path) -> None:
        """A direct save/load must not depend on a UI-readable sidecar file."""
        lightgbm = pytest.importorskip("lightgbm")
        from pyrobot.ai.training import OptionalLightGBMDirectionModel

        rng = np.random.default_rng(5)
        X = pd.DataFrame({"a": rng.normal(size=80), "b": rng.normal(size=80)})
        y = pd.Series((0.3 * X["a"] - 0.2 * X["b"] > 0).astype(int))
        model = OptionalLightGBMDirectionModel(model_id="sc", version="v2", n_estimators=50).fit(X, y)
        path = tmp_path / "model.npz"
        model.save(path)

        # Remove the informative sidecar — reloading must still fully work.
        path.with_suffix(".meta.json").unlink()
        restored = OptionalLightGBMDirectionModel.load(path)
        assert restored.params["n_estimators"] == 50
        assert restored.feature_names == ["a", "b"]
        np.testing.assert_allclose(
            restored.predict_proba(X), model.predict_proba(X), atol=1e-10
        )
