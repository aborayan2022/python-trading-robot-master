"""Unit tests for Research-Grade Backtesting, Cost Model, Metrics, Walk-Forward, and Monte Carlo."""

import numpy as np
import pandas as pd

from pyrobot.backtesting import (
    CostModelConfig,
    ExecutionCostModel,
    MonteCarloSimulator,
    WalkForwardValidator,
    calculate_quantitative_metrics,
    run_walk_forward,
)


class TestExecutionCostModel:

    def test_buy_order_fill_cost(self):
        model = ExecutionCostModel()
        fill = model.calculate_fill(
            side="BUY",
            quantity=100,
            price=150.0,
            bar_volume=50000.0,
            volatility=0.015,
        )

        assert fill["filled_qty"] == 100
        # Buy price should be slightly higher than raw price due to spread + slippage + impact
        assert fill["fill_price"] > 150.0
        assert fill["total_commission"] >= 1.0  # Min commission
        assert fill["sec_fee"] == 0.0  # SEC fee only on sells

    def test_sell_order_includes_sec_fee(self):
        model = ExecutionCostModel()
        fill = model.calculate_fill(
            side="SELL",
            quantity=100,
            price=150.0,
            bar_volume=50000.0,
            volatility=0.015,
        )

        assert fill["filled_qty"] == 100
        # Sell price should be lower than raw price
        assert fill["fill_price"] < 150.0
        assert fill["sec_fee"] > 0.0

    def test_partial_fill_on_large_order(self):
        config = CostModelConfig(max_volume_participation=0.05) # 5% of volume max
        model = ExecutionCostModel(config=config)
        fill = model.calculate_fill(
            side="BUY",
            quantity=1000,
            price=100.0,
            bar_volume=10000.0,  # 5% max = 500 shares
        )

        assert fill["filled_qty"] == 500


class TestQuantitativeMetrics:

    def test_metrics_calculation(self):
        daily_returns = [0.01, -0.005, 0.008, 0.012, -0.003, 0.006, -0.002, 0.015]
        equity_curve = [100000, 101000, 100495, 101299, 102514, 102206, 102819, 102613, 104152]
        trades = [
            {"pnl": 1000.0},
            {"pnl": -505.0},
            {"pnl": 804.0},
            {"pnl": 1215.0},
            {"pnl": -308.0},
        ]

        report = calculate_quantitative_metrics(daily_returns, equity_curve, trades)
        assert report.total_return_pct > 0
        assert report.sharpe_ratio > 0
        assert report.win_rate_pct == 60.0
        assert report.total_trades == 5
        assert report.expectancy_per_trade > 0


class TestWalkForwardValidator:

    def test_walk_forward_splits(self):
        dates = pd.date_range("2023-01-01", periods=400, freq="B")
        df = pd.DataFrame({"close": np.random.randn(400)}, index=dates)

        validator = WalkForwardValidator(
            n_splits=3,
            train_period_days=180,
            test_period_days=40,
            embargo_days=5,
        )

        splits = list(validator.split(df))
        assert len(splits) == 3

        for s in splits:
            assert len(s.train_indices) > 0
            assert len(s.test_indices) > 0
            # Test must be strictly after train + embargo
            assert s.test_start > s.train_end


class TestMonteCarloSimulator:

    def test_monte_carlo_resampling(self):
        trades = [
            {"pnl": 500},
            {"pnl": -300},
            {"pnl": 800},
            {"pnl": -400},
            {"pnl": 1200},
            {"pnl": -200},
        ]

        mc = MonteCarloSimulator(n_simulations=200, initial_capital=50000.0, seed=42)
        report = mc.run(trades)

        assert report.simulations == 200
        assert report.median_return_pct > 0
        assert 0.0 <= report.ruin_probability_pct <= 100.0

    def test_monte_carlo_deterministic_with_seed(self):
        trades = [{"pnl": p} for p in (500, -300, 800, -400, 1200, -200, 90, -60)]
        mc1 = MonteCarloSimulator(n_simulations=300, seed=7)
        mc2 = MonteCarloSimulator(n_simulations=300, seed=7)
        r1, r2 = mc1.run(trades), mc2.run(trades)
        assert r1.median_return_pct == r2.median_return_pct
        assert r1.p5_return_pct == r2.p5_return_pct
        assert r1.median_max_drawdown_pct == r2.median_max_drawdown_pct
        assert r1.ruin_probability_pct == r2.ruin_probability_pct

    def test_ruin_detected_on_drawdown_paths(self):
        # Losing 30%+ from peak on a 25% ruin threshold must register as ruined.
        trades = [{"pnl": 2000}, {"pnl": 2000}, {"pnl": -10000}, {"pnl": 2000}]
        mc = MonteCarloSimulator(n_simulations=500, initial_capital=10000.0,
                                 ruin_threshold_pct=0.25, seed=3)
        report = mc.run(trades)
        assert report.ruin_probability_pct > 0


class TestRunWalkForward:

    def test_walk_forward_end_to_end(self):
        """Re-fit per fold; OOS predictions cover exactly the test folds."""
        rng = np.random.default_rng(11)
        dates = pd.date_range("2023-01-01", periods=200, freq="B")
        X = pd.DataFrame({
            "f1": rng.normal(size=200),
            "f2": rng.normal(size=200),
        }, index=dates)
        true_w = np.array([2.0, -1.5])
        y = pd.Series(X.to_numpy() @ true_w + 0.05 * rng.normal(size=200), index=dates)

        class TinyLinearModel:
            def fit(self, frame, labels):
                self.w = np.linalg.lstsq(frame.to_numpy(), labels.to_numpy(), rcond=None)[0]

            def predict(self, frame):
                return frame.to_numpy() @ self.w

        def metric_fn(y_true, y_pred):
            residual = y_true.to_numpy() - y_pred
            ss_res = float((residual ** 2).sum())
            ss_tot = float(((y_true.to_numpy() - y_true.to_numpy().mean()) ** 2).sum())
            return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        result = run_walk_forward(
            features=X,
            labels=y,
            model_factory=TinyLinearModel,
            train_fn=lambda m, feats, lbls: m.fit(feats, lbls),
            predict_fn=lambda m, f: m.predict(f),
            metric_fn=metric_fn,
            n_splits=4,
            train_period_days=100,
            test_period_days=20,
            embargo_days=5,
            expanding=True,
        )

        assert len(result.fold_scores) == 4
        # Every fold's noisy-linear model generalizes: R^2 well above zero OOS.
        assert result.oos_score > 0.5
        assert len(result.oos_predictions) == sum(20 for _ in range(4))
        assert len(result.oos_labels) == len(result.oos_predictions)
        assert "oos_score" in result.summary()

    def test_walk_forward_no_test_overlap_with_train(self):
        """Concatenated OOS indices never intersect any fold's train indices."""
        dates = pd.date_range("2023-01-01", periods=200, freq="B")
        X = pd.DataFrame({"f1": np.linspace(-1, 1, 200)}, index=dates)
        pd.Series(3.0 * X["f1"], index=dates)

        validator = WalkForwardValidator(
            n_splits=3, train_period_days=100, test_period_days=25, embargo_days=5,
        )
        covered_test = []
        for split in validator.split(X):
            overlap = set(split.train_indices) & set(split.test_indices)
            assert overlap == set()
            covered_test.extend(split.test_indices.tolist())
        assert len(covered_test) == len(set(covered_test))  # test folds disjoint
