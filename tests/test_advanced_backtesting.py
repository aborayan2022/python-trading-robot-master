"""Unit tests for Research-Grade Backtesting, Cost Model, Metrics, Walk-Forward, and Monte Carlo."""

import pytest
import pandas as pd
import numpy as np

from pyrobot.backtesting import (
    ExecutionCostModel,
    CostModelConfig,
    calculate_quantitative_metrics,
    WalkForwardValidator,
    MonteCarloSimulator,
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
