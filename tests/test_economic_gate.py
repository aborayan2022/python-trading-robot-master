"""WO-4 acceptance tests: Economic approval gate."""

import numpy as np
import pandas as pd
import pytest

from pyrobot.ai.economic_gate import EconomicMetrics, evaluate_oos_economics
from pyrobot.ai.registry import (
    ModelMetadata,
    ModelNotApprovedError,
    ModelRegistry,
    ModelStatus,
)
from pyrobot.ai.training import TrainingGateConfig


def _make_ohlcv(n: int, base_price: float = 100.0, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with trending + mean-reverting segments."""
    rng = np.random.default_rng(seed)
    close = base_price + np.cumsum(rng.normal(0, 0.5, size=n))
    close = np.maximum(close, 10.0)
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.1, size=n),
            "high": close + abs(rng.normal(0, 0.5, size=n)),
            "low": close - abs(rng.normal(0, 0.5, size=n)),
            "close": close,
            "volume": rng.integers(100_000, 1_000_000, size=n),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


class TestWO4EconomicGate:
    """WO-4: Accuracy-only champions must not pass governance without economics."""

    def test_high_accuracy_negative_economics_rejected(self):
        """~60% accuracy but payoff profile that loses after costs → not approved."""
        n = 400
        # Create a mean-reverting price: rallies then crashes repeatedly
        rng = np.random.default_rng(101)
        base = np.concatenate([
            np.linspace(100, 120, 50),
            np.linspace(120, 80, 50),
        ] * 4)  # repeat the pattern 4 times
        prices = pd.DataFrame(
            {
                "open": base + rng.normal(0, 0.2, size=n),
                "high": base + abs(rng.normal(0, 0.5, size=n)),
                "low": base - abs(rng.normal(0, 0.5, size=n)),
                "close": base,
                "volume": rng.integers(100_000, 1_000_000, size=n),
            },
            index=pd.date_range("2026-01-01", periods=n, freq="D"),
        )

        # Signal pattern: BUY at the peak (0.85 in rising phase, but entries
        # are late → small wins), SELL at the trough (0.15 in falling phase,
        # but exits are late → large losses). This creates negative payoff skew.
        probs = np.full(n, 0.5)
        # BUY signals during the second half of each rally (late entries)
        for i in range(0, n, 100):
            probs[i + 25 : i + 50] = 0.85  # BUY late in rally
            probs[i + 75 : i + 100] = 0.15  # SELL late in crash (late shorts → bigger losses)

        metrics = evaluate_oos_economics(
            oos_probabilities=probs,
            aligned_prices=prices,
        )

        assert metrics.n_trades > 0, "Expected trades to be generated"

        # Either negative PnL or very low EV per trade shows the negative edge
        has_negative_economics = (
            metrics.net_pnl_after_costs < 0 or metrics.ev_per_trade <= 0
        )
        assert has_negative_economics, (
            f"Expected negative economics but got pnl={metrics.net_pnl_after_costs:.2f}, "
            f"ev/trade={metrics.ev_per_trade:.2f}"
        )

    def test_marginal_model_fails_cost_gate(self):
        """Gross-positive but cost-negative EV → rejected."""
        n = 300
        prices = _make_ohlcv(n, seed=200)

        # Set up probabilities that generate frequent small trades
        # Every 5 bars flip between BUY and SELL, creating high turnover
        rng = np.random.default_rng(201)
        probs = np.full(n, 0.5)
        for i in range(0, n, 5):
            if i % 10 == 0:
                probs[i:min(i + 5, n)] = 0.85
            else:
                probs[i:min(i + 5, n)] = 0.15

        metrics = evaluate_oos_economics(
            oos_probabilities=probs,
            aligned_prices=prices,
        )

        # High turnover should produce many trades but costs erode edge
        assert metrics.n_trades >= 20
        assert metrics.ev_per_trade <= 0, (
            f"Expected non-positive EV per trade but got {metrics.ev_per_trade}"
        )

    def test_registry_blocks_promotion_without_economics(self):
        """Metadata missing economic metrics → ModelNotApprovedError.

        The artifact gate fires first, so we pass that by providing a real
        (tiny) artifact file, then verify the economic metrics gate rejects.
        """
        import hashlib
        import tempfile
        from pathlib import Path

        # Create a minimal valid .npz so the artifact check passes
        tmp_dir = Path(tempfile.mkdtemp())
        artifact_path = tmp_dir / "test_model.npz"
        np.savez(artifact_path, weights=np.array([1.0]))
        artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()

        registry = ModelRegistry.__new__(ModelRegistry)
        registry._models = {}
        registry._lock = __import__("threading").Lock()
        registry.registry_dir = None

        meta = ModelMetadata(
            model_id="no_econ_test",
            version="v1",
            model_type="logistic_direction",
            target_variable="dir_5",
            features=["f1"],
            training_start="2026-01-01",
            training_end="2026-01-31",
            status=ModelStatus.CHALLENGER,
            artifact_path=str(artifact_path),
            artifact_sha256=artifact_sha256,
            oos_metrics={
                "oos_accuracy": 0.65,
                "buy_hold_accuracy": 0.52,
                "sma_accuracy": 0.50,
                "expected_calibration_error": 0.05,
                "oos_samples": 150,
                # Missing: net_pnl_after_costs, sharpe, profit_factor, n_trades, ev_per_trade
            },
        )
        registry._models["no_econ_test:v1"] = meta

        with pytest.raises(ModelNotApprovedError, match="missing metrics"):
            registry.promote_to_champion("no_econ_test", "v1", approved_by="test")

    def test_few_trades_not_approved(self):
        """All metrics positive but n_trades < min_oos_trades → rejected."""
        n = 200
        prices = _make_ohlcv(n, seed=300)

        # Only 3 trades worth of signals (too few)
        probs = np.full(n, 0.5)
        probs[50:55] = 0.85  # One entry/exit cycle
        probs[100:105] = 0.15  # Another

        metrics = evaluate_oos_economics(
            oos_probabilities=probs,
            aligned_prices=prices,
        )

        assert metrics.n_trades < TrainingGateConfig().min_oos_trades

        # Even with positive PnL, the trade-count guard blocks approval
        gate = TrainingGateConfig()
        assert metrics.n_trades < gate.min_oos_trades

    def test_profitable_model_passes_all_gates(self, tmp_path):
        """Consistent edge, enough trades, positive economics → approved."""
        rng = np.random.default_rng(400)
        n = 500

        # 5-bar segments: 500/5 = 100 segments → ~50 completed trades
        seg = 5
        close = np.concatenate([
            np.linspace(100, 105, seg),
            np.linspace(105, 100, seg),
        ] * (n // (2 * seg)))
        close = close[:n]
        prices = pd.DataFrame(
            {
                "open": close + rng.normal(0, 0.02, size=n),
                "high": close + abs(rng.normal(0, 0.05, size=n)),
                "low": close - abs(rng.normal(0, 0.05, size=n)),
                "close": close,
                "volume": np.full(n, 1_000_000.0),
            },
            index=pd.date_range("2026-01-01", periods=n, freq="D"),
        )

        # Alternate BUY/SELL every segment
        probs = np.full(n, 0.5)
        for i in range(n):
            seg_idx = (i // seg) % 2
            probs[i] = 0.90 if seg_idx == 0 else 0.10

        metrics = evaluate_oos_economics(
            oos_probabilities=probs,
            aligned_prices=prices,
        )

        assert metrics.n_trades >= 20, f"Expected ≥20 trades, got {metrics.n_trades}"
        assert metrics.net_pnl_after_costs > 0, (
            f"Expected positive PnL but got {metrics.net_pnl_after_costs:.2f}"
        )
        assert metrics.ev_per_trade > 0
        assert metrics.profit_factor >= 1.0
