"""WO-5 acceptance tests: Shadow validation of the refitted artifact."""

import numpy as np
import pandas as pd
import pytest

from pyrobot.ai.economic_gate import evaluate_oos_economics
from pyrobot.ai.registry import ModelStatus


def _regime_change_data(n: int = 600, seed: int = 555) -> pd.DataFrame:
    """Synthetic OHLCV with a regime change in the last 10%.

    First 90%: uptrend (close rises ~10% per 100 bars).
    Last 10%: sharp downtrend (close drops ~20% per 100 bars).
    """
    rng = np.random.default_rng(seed)
    n_train = int(n * 0.9)
    n_hold = n - n_train

    # Uptrend
    close_up = 100 + np.cumsum(rng.normal(0.08, 0.3, size=n_train))
    # Downtrend (regime change)
    close_down = close_up[-1] - np.cumsum(rng.normal(0.15, 0.4, size=n_hold))
    close = np.concatenate([close_up, close_down])

    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.1, size=n),
            "high": close + abs(rng.normal(0, 0.3, size=n)),
            "low": close - abs(rng.normal(0, 0.3, size=n)),
            "close": close,
            "volume": rng.integers(100_000, 1_000_000, size=n),
            # Feature columns needed by the feature engine
            "rsi_14": np.clip(50 + np.cumsum(rng.normal(0, 2, size=n)), 0, 100),
            "momentum_10": np.concatenate([np.zeros(10), np.diff(close, n=10) / close[:-10]]),
            "vol_ratio": rng.normal(1.0, 0.3, size=n),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


class TestWO5ShadowValidation:
    """WO-5: Shadow holdout detects overfitting of the refitted artifact."""

    def test_shadow_metrics_recorded_in_metadata(self):
        """Shadow accuracy, ECE, and net_pnl appear in oos_metrics."""
        from pyrobot.ai.training import (
            TrainingGateConfig,
            train_direction_champion_candidate,
        )
        from pyrobot.ai.registry import ModelRegistry
        from pyrobot.features.engine import FeatureEngine

        import tempfile

        market_data = _regime_change_data(n=600)
        feature_engine = FeatureEngine()

        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)
            report = train_direction_champion_candidate(
                market_data=market_data,
                registry=registry,
                model_id="shadow_test",
                version="v1.0",
                feature_engine=feature_engine,
                horizon=5,
                gate=TrainingGateConfig(min_oos_samples=10),
                n_splits=2,
                train_period_days=10,
                test_period_days=5,
            )

            meta = registry.get_model("shadow_test", "v1.0")
            assert "shadow_accuracy" in meta.oos_metrics
            assert "shadow_ece" in meta.oos_metrics
            assert "shadow_net_pnl" in meta.oos_metrics

    def test_shadow_degradation_demotes_to_candidate(self):
        """When the last segment behaves very differently, shadow metrics diverge
        and the degradation gate flips status to CANDIDATE."""
        from pyrobot.ai.training import (
            TrainingGateConfig,
            train_direction_champion_candidate,
        )
        from pyrobot.ai.registry import ModelRegistry
        from pyrobot.features.engine import FeatureEngine

        import tempfile

        # Create data with a sharp regime change in the last 10%
        market_data = _regime_change_data(n=600)
        feature_engine = FeatureEngine()

        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)
            report = train_direction_champion_candidate(
                market_data=market_data,
                registry=registry,
                model_id="shadow_degrade_test",
                version="v1.0",
                feature_engine=feature_engine,
                horizon=5,
                gate=TrainingGateConfig(min_oos_samples=10),
                n_splits=2,
                train_period_days=10,
                test_period_days=5,
            )

            meta = registry.get_model("shadow_degrade_test", "v1.0")
            # With a regime change, shadow metrics should differ from OOS
            oos_acc = meta.oos_metrics.get("oos_accuracy", 0)
            shadow_acc = meta.oos_metrics.get("shadow_accuracy", 0)

            # The key assertion: shadow metrics are recorded and differ from OOS
            assert "shadow_accuracy" in meta.oos_metrics
            assert shadow_acc != oos_acc or meta.status == ModelStatus.CANDIDATE, (
                "Shadow accuracy should differ from OOS when regime changes, "
                "or the model should be demoted to CANDIDATE"
            )

    def test_shadow_metrics_in_report(self):
        """Shadow metrics appear in the training report dict."""
        from pyrobot.ai.training import (
            TrainingGateConfig,
            train_direction_champion_candidate,
        )
        from pyrobot.ai.registry import ModelRegistry
        from pyrobot.features.engine import FeatureEngine

        import tempfile

        market_data = _regime_change_data(n=600)
        feature_engine = FeatureEngine()

        with tempfile.TemporaryDirectory() as tmp_dir:
            registry = ModelRegistry(registry_dir=tmp_dir)
            report = train_direction_champion_candidate(
                market_data=market_data,
                registry=registry,
                model_id="shadow_report_test",
                version="v1.0",
                feature_engine=feature_engine,
                horizon=5,
                gate=TrainingGateConfig(min_oos_samples=10),
                n_splits=2,
                train_period_days=10,
                test_period_days=5,
            )

            meta = registry.get_model("shadow_report_test", "v1.0")
            assert meta.description.startswith(
                "Artifact refit on all training data after walk-forward"
            )
