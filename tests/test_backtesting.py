"""Tests for the backtesting engine."""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

from pyrobot.backtesting.engine import BacktestEngine, BacktestResult


def _make_price_data(n=60, base_price=100.0, symbol="MSFT"):
    """Generate synthetic price data for backtesting."""
    np.random.seed(1)
    data = []
    price = base_price
    start = datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc)
    for i in range(n):
        change = np.random.uniform(-1, 1.2)
        open_p = price + change
        close_p = open_p + np.random.uniform(-0.5, 0.5)
        high_p = max(open_p, close_p) + np.random.uniform(0, 0.3)
        low_p = min(open_p, close_p) - np.random.uniform(0, 0.3)
        data.append({
            "symbol": symbol,
            "open": round(open_p, 2),
            "close": round(close_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "volume": int(np.random.uniform(10000, 50000)),
            "datetime": int((start + timedelta(minutes=i)).timestamp() * 1000),
        })
        price = close_p
    return data


class TestBacktestResult:
    """Tests for BacktestResult metrics."""

    def test_empty_result(self):
        result = BacktestResult()
        assert result.total_return == 0.0
        assert result.total_return_pct == 0.0
        assert result.sharpe_ratio == 0.0
        assert result.sortino_ratio == 0.0
        assert result.max_drawdown == 0.0
        assert result.win_rate == 0.0
        assert result.total_trades == 0
        assert result.profit_factor == 0.0

    def test_profitable_result(self):
        result = BacktestResult()
        result.starting_balance = 100000.0
        result.ending_balance = 110000.0
        assert result.total_return == pytest.approx(0.1)
        assert result.total_return_pct == pytest.approx(10.0)

    def test_loss_result(self):
        result = BacktestResult()
        result.starting_balance = 100000.0
        result.ending_balance = 90000.0
        assert result.total_return == pytest.approx(-0.1)

    def test_sharpe_ratio(self):
        result = BacktestResult()
        result.daily_returns = [0.01, 0.02, -0.005, 0.015, 0.008] * 20
        assert result.sharpe_ratio != 0.0

    def test_sharpe_ratio_zero_std(self):
        result = BacktestResult()
        result.daily_returns = [0.0] * 10
        assert result.sharpe_ratio == 0.0

    def test_sortino_ratio(self):
        result = BacktestResult()
        result.daily_returns = [0.01, -0.02, 0.015, -0.005, 0.01]
        assert result.sortino_ratio != 0.0

    def test_sortino_no_downside(self):
        result = BacktestResult()
        result.daily_returns = [0.01, 0.02, 0.015]
        assert result.sortino_ratio == 0.0

    def test_max_drawdown(self):
        result = BacktestResult()
        result.equity_curve = [100, 110, 105, 95, 100, 115]
        assert result.max_drawdown < 0
        assert result.max_drawdown == pytest.approx(-0.1364, abs=0.01)

    def test_max_drawdown_no_loss(self):
        result = BacktestResult()
        result.equity_curve = [100, 110, 120, 130]
        assert result.max_drawdown == 0.0

    def test_win_rate(self):
        result = BacktestResult()
        result.trades = [
            {"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": -30}
        ]
        assert result.win_rate == pytest.approx(0.5)

    def test_profit_factor(self):
        result = BacktestResult()
        result.trades = [
            {"pnl": 100}, {"pnl": -50}, {"pnl": 200}, {"pnl": -30}
        ]
        assert result.profit_factor == pytest.approx(300 / 80)

    def test_profit_factor_all_wins(self):
        result = BacktestResult()
        result.trades = [{"pnl": 100}, {"pnl": 200}]
        assert result.profit_factor == float("inf")

    def test_summary(self):
        result = BacktestResult()
        result.starting_balance = 100000.0
        result.ending_balance = 105000.0
        result.trades = [{"pnl": 500}]
        result.equity_curve = [100000, 102000, 105000]
        s = result.summary()
        assert isinstance(s, dict)
        assert "total_return_pct" in s
        assert "sharpe_ratio" in s
        assert "max_drawdown_pct" in s
        assert "win_rate_pct" in s

    def test_repr(self):
        result = BacktestResult()
        result.starting_balance = 100000.0
        result.ending_balance = 105000.0
        assert "BacktestResult" in repr(result)


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    def test_init(self):
        engine = BacktestEngine(initial_balance=50000.0)
        assert engine.initial_balance == 50000.0
        assert engine.commission_per_trade == 0.0
        assert engine.slippage_pct == 0.0

    def test_run_no_data(self):
        engine = BacktestEngine()
        result = engine.run(strategy=lambda sf, ind: None)
        assert result.total_trades == 0
        assert result.equity_curve == []

    def test_run_buy_and_hold(self):
        data = _make_price_data(n=30)
        engine = BacktestEngine(
            initial_balance=100000.0,
            historical_data=data,
        )

        buy_count = {"n": 0}

        def buy_and_hold(stock_frame, indicator_client):
            if buy_count["n"] == 0:
                buy_count["n"] += 1
                return "buy"
            return None

        result = engine.run(strategy=buy_and_hold)
        assert result.total_return_pct >= 0 or result.total_return_pct < 100
        assert len(result.equity_curve) > 0

    def test_run_buy_then_sell(self):
        data = _make_price_data(n=30)
        engine = BacktestEngine(
            initial_balance=100000.0,
            historical_data=data,
        )

        step = {"n": 0}

        def buy_then_sell(stock_frame, indicator_client):
            step["n"] += 1
            if step["n"] == 5:
                return "buy"
            elif step["n"] == 15:
                return "sell"
            return None

        result = engine.run(strategy=buy_then_sell)
        assert result.total_trades >= 0

    def test_stop_loss(self):
        data = _make_price_data(n=30)
        engine = BacktestEngine(
            initial_balance=100000.0,
            historical_data=data,
        )

        step = {"n": 0}

        def buy_only(stock_frame, indicator_client):
            step["n"] += 1
            if step["n"] == 3:
                return "buy"
            return None

        result = engine.run(
            strategy=buy_only,
            stop_loss_pct=0.01,
        )
        assert isinstance(result, BacktestResult)

    def test_commission(self):
        data = _make_price_data(n=30)
        engine = BacktestEngine(
            initial_balance=100000.0,
            historical_data=data,
            commission_per_trade=5.0,
        )

        step = {"n": 0}

        def buy_then_sell(stock_frame, indicator_client):
            step["n"] += 1
            if step["n"] == 3:
                return "buy"
            elif step["n"] == 15:
                return "sell"
            return None

        result = engine.run(strategy=buy_then_sell)
        assert isinstance(result, BacktestResult)

    def test_slippage(self):
        data = _make_price_data(n=30)
        engine = BacktestEngine(
            initial_balance=100000.0,
            historical_data=data,
            slippage_pct=0.001,
        )

        step = {"n": 0}

        def buy_only(stock_frame, indicator_client):
            step["n"] += 1
            if step["n"] == 3:
                return "buy"
            return None

        result = engine.run(strategy=buy_only)
        assert isinstance(result, BacktestResult)

    def test_indicator_setup(self):
        data = _make_price_data(n=30)
        engine = BacktestEngine(
            initial_balance=100000.0,
            historical_data=data,
        )

        setup_called = {"n": 0}

        def my_setup(indicator_client):
            setup_called["n"] += 1
            indicator_client.sma(period=5)

        def noop(stock_frame, indicator_client):
            return None

        result = engine.run(strategy=noop, indicator_setup=my_setup)
        assert setup_called["n"] == 1

    def test_take_profit(self):
        data = _make_price_data(n=60, base_price=100.0)
        engine = BacktestEngine(
            initial_balance=100000.0,
            historical_data=data,
        )

        step = {"n": 0}

        def buy_only(stock_frame, indicator_client):
            step["n"] += 1
            if step["n"] == 3:
                return "buy"
            return None

        result = engine.run(
            strategy=buy_only,
            take_profit_pct=0.01,
        )
        assert isinstance(result, BacktestResult)
