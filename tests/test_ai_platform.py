"""Unit tests for the AI & Machine Learning Quantitative Platform."""

import pytest
import numpy as np
import pandas as pd
import tempfile
from datetime import datetime, timezone

from pyrobot.ai import (
    ModelRegistry,
    ModelMetadata,
    ModelStatus,
    GBDTDirectionClassifier,
    VolatilityForecaster,
    EnsembleSignalEngine,
    DriftDetector,
    LLMContextEngine,
    NewsEventType,
)
from pyrobot.exceptions import ModelNotFoundError
from pyrobot.models.signal import SignalAction


class TestModelRegistry:
    def test_champion_challenger_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)

            m1 = ModelMetadata(
                model_id="xgb_direction",
                version="v1.0",
                model_type="GBDT_Classifier",
                target_variable="return_5d_sign",
                features=["rsi_14", "vol_ratio"],
                training_start="2024-01-01",
                training_end="2025-01-01",
                status=ModelStatus.CANDIDATE,
            )
            registry.register_model(m1)

            # Retrieve model
            loaded = registry.get_model("xgb_direction", "v1.0")
            assert loaded.model_id == "xgb_direction"
            assert loaded.status == ModelStatus.CANDIDATE

            # Promote to Champion
            champ = registry.promote_to_champion("xgb_direction", "v1.0", approved_by="RiskCommittee")
            assert champ.status == ModelStatus.CHAMPION
            assert registry.get_champion().version == "v1.0"

            # Register second model and promote to Challenger
            m2 = ModelMetadata(
                model_id="xgb_direction",
                version="v2.0",
                model_type="GBDT_Classifier",
                target_variable="return_5d_sign",
                features=["rsi_14", "vol_ratio", "momentum"],
                training_start="2024-01-01",
                training_end="2025-06-01",
            )
            registry.register_model(m2)
            registry.promote_to_challenger("xgb_direction", "v2.0")

            challengers = registry.get_challengers()
            assert len(challengers) == 1
            assert challengers[0].version == "v2.0"

            # Promote Challenger v2.0 to Champion -> v1.0 should be archived
            registry.promote_to_champion("xgb_direction", "v2.0", approved_by="RiskCommittee")
            assert registry.get_champion().version == "v2.0"
            assert registry.get_model("xgb_direction", "v1.0").status == ModelStatus.ARCHIVED


class TestQuantModels:
    def test_gbdt_direction_classifier(self) -> None:
        np.random.seed(42)
        n = 100
        X = pd.DataFrame({
            "rsi_14": np.random.uniform(20, 80, n),
            "momentum_10": np.random.normal(0, 1, n),
        })
        # Synthetic target correlated with features
        logits = 0.05 * (X["rsi_14"] - 50) + 0.5 * X["momentum_10"]
        y = pd.Series((logits > 0).astype(int))

        clf = GBDTDirectionClassifier(model_id="test_clf", n_estimators=20)
        clf.fit(X, y)

        assert clf.is_fitted
        assert len(clf.feature_importances_) == 2

        probs = clf.predict_proba(X.iloc[:5])
        assert probs.shape == (5, 2)
        assert np.allclose(probs[:, 0] + probs[:, 1], 1.0)

        preds = clf.predict(X.iloc[:5])
        assert len(preds) == 5

    def test_volatility_forecaster(self) -> None:
        np.random.seed(42)
        n = 80
        X = pd.DataFrame({
            "hist_vol_20": np.random.uniform(0.01, 0.05, n),
            "atr_ratio": np.random.uniform(0.8, 1.5, n),
        })
        y = pd.Series(0.8 * X["hist_vol_20"] + 0.01 * X["atr_ratio"])

        reg = VolatilityForecaster(model_id="test_vol")
        reg.fit(X, y)

        assert reg.is_fitted
        preds = reg.predict(X.iloc[:5])
        assert len(preds) == 5
        assert (preds > 0).all()


class TestEnsembleSignalEngine:
    def test_ensemble_generates_signal(self) -> None:
        dates = pd.date_range("2026-01-01", periods=30, freq="D", tz="UTC")
        df = pd.DataFrame({
            "open": np.linspace(100, 130, 30),
            "high": np.linspace(102, 132, 30),
            "low": np.linspace(99, 129, 30),
            "close": np.linspace(101, 131, 30),
            "volume": [10000] * 30,
            "rsi_14": [70] * 30,
            "momentum_10": [0.05] * 30,
        }, index=dates)

        clf = GBDTDirectionClassifier()
        clf.fit(df[["rsi_14", "momentum_10"]], pd.Series([1] * 30))

        engine = EnsembleSignalEngine(direction_model=clf)
        signal = engine.generate_signal(
            symbol="AAPL",
            features_df=df,
            current_price=131.0,
        )

        assert signal.symbol == "AAPL"
        assert signal.probability >= 0.5
        assert signal.confidence >= 0.0


class TestDriftDetector:
    def test_psi_and_drift_detection(self) -> None:
        np.random.seed(42)
        baseline = pd.DataFrame({"feature_a": np.random.normal(0, 1, 500)})
        # Same distribution -> no drift
        current_stable = pd.DataFrame({"feature_a": np.random.normal(0, 1, 500)})

        detector = DriftDetector()
        report_stable = detector.evaluate_drift(baseline, current_stable)
        assert report_stable.is_drift_detected is False
        assert report_stable.max_psi < 0.10

        # Shifted distribution -> drift detected
        current_shifted = pd.DataFrame({"feature_a": np.random.normal(3.0, 1, 500)})
        report_shifted = detector.evaluate_drift(baseline, current_shifted)
        assert report_shifted.is_drift_detected is True
        assert report_shifted.max_psi >= 0.25
        assert "feature_a" in report_shifted.flagged_features


class TestLLMContextEngine:
    def test_headline_analysis(self) -> None:
        engine = LLMContextEngine()
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

    def test_trade_explainability(self) -> None:
        engine = LLMContextEngine()
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
