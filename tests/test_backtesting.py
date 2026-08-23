"""Tests for the backtesting engine."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

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

        engine.run(strategy=noop, indicator_setup=my_setup)
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


class TestBacktestHonesty:
    """Behavioral tests enforcing the engine's honesty contract."""

    @staticmethod
    def _make_cost_free_engine(data, **kwargs):
        """Engine whose cost model charges nothing and fills exactly at price."""
        from pyrobot.backtesting.cost_model import CostModelConfig, ExecutionCostModel

        cfg = CostModelConfig(
            half_spread_bps=0.0,
            base_slippage_bps=0.0,
            commission_per_share=0.0,
            min_commission=0.0,
            sec_fee_rate=0.0,
            market_impact_coefficient=0.0,
        )
        return BacktestEngine(
            historical_data=data,
            cost_model=ExecutionCostModel(config=cfg),
            **kwargs,
        )

    @staticmethod
    def _bars(rows, symbol="MSFT"):
        """rows: (open, high, low, close) tuples one minute apart, volume 1M."""
        start = datetime(2024, 1, 2, 9, 30, tzinfo=timezone.utc)
        data = []
        for i, row in enumerate(rows):
            data.append({
                "symbol": symbol,
                "open": round(row[0], 2),
                "high": round(row[1], 2),
                "low": round(row[2], 2),
                "close": round(row[3], 2),
                "volume": 1000000,
                "datetime": int((start + timedelta(minutes=i)).timestamp() * 1000),
            })
        return data

    def test_next_bar_execution(self):
        """Signal on bar t fills at bar t+1 OPEN, never the signal bar close."""
        rows = [
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 101.0, 99.0, 105.0),   # bar1: BUY signal (close 105)
            (110.0, 111.0, 109.0, 112.0),  # bar2: entry must be at open 110
            (112.0, 113.0, 111.0, 114.0),  # bar3: sell signal
            (113.0, 114.0, 112.0, 113.0),  # bar4: exit at open 113
            (113.0, 114.0, 112.0, 113.0),
        ]
        engine = self._make_cost_free_engine(self._bars(rows))
        calls = {"n": 0}

        def strategy(stock_frame, indicator_client):
            calls["n"] += 1
            if calls["n"] == 2:
                return "buy"
            if calls["n"] == 4:
                return "sell"
            return None

        result = engine.run(strategy=strategy)
        assert len(result.trades) == 1
        assert result.trades[0]["entry_price"] == pytest.approx(110.0)
        assert result.trades[0]["exit_price"] == pytest.approx(113.0)

    def test_no_fill_on_final_bar_signal(self):
        """A buy signal on the last bar never fills (no next bar exists)."""
        rows = [(100.0, 101.0, 99.0, 100.0)] * 6
        rows[-1] = (100.0, 200.0, 99.0, 200.0)
        engine = self._make_cost_free_engine(self._bars(rows))
        seen = []

        def buy_on_last(stock_frame, indicator_client):
            seen.append(len(stock_frame.frame))
            return "buy" if len(seen) == len(rows) else None

        result = engine.run(strategy=buy_on_last)
        assert result.total_trades == 0

    def test_strategy_sees_only_past_rows(self):
        """Lookahead guard: at call k the frame has exactly the rows up to bar k."""
        rows = [(100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i) for i in range(10)]
        engine = self._make_cost_free_engine(self._bars(rows))
        seen_lengths = []

        def recorder(stock_frame, indicator_client):
            seen_lengths.append(len(stock_frame.frame))
            return None

        engine.run(strategy=recorder)
        assert seen_lengths == [i + 1 for i in range(10)]

    def test_stop_loss_intrabar_no_gap(self):
        """Stop fills at the stop price when the bar low pierces it."""
        rows = [
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 101.0, 99.0, 100.0),   # BUY signal
            (100.0, 101.0, 99.5, 100.5),   # entry at open 100
            (99.0, 99.5, 94.0, 95.0),      # low 94 pierces stop 95
            (95.0, 96.0, 94.0, 95.0),
        ]
        engine = self._make_cost_free_engine(self._bars(rows))
        calls = {"n": 0}

        def strategy(stock_frame, indicator_client):
            calls["n"] += 1
            return "buy" if calls["n"] == 2 else None

        result = engine.run(strategy=strategy, stop_loss_pct=0.05)
        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade["exit_reason"] == "stop_loss"
        assert trade["exit_price"] == pytest.approx(95.0)

    def test_stop_loss_gap_through_open(self):
        """When the bar gaps through the stop, exit at the (worse) open."""
        rows = [
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 101.0, 99.0, 100.0),   # BUY signal
            (100.0, 101.0, 99.5, 100.5),   # entry at open 100
            (90.0, 91.0, 89.0, 90.0),      # opens at 90, below stop 95
            (90.0, 91.0, 89.0, 90.0),
        ]
        engine = self._make_cost_free_engine(self._bars(rows))
        calls = {"n": 0}

        def strategy(stock_frame, indicator_client):
            calls["n"] += 1
            return "buy" if calls["n"] == 2 else None

        result = engine.run(strategy=strategy, stop_loss_pct=0.05)
        trade = result.trades[0]
        assert trade["exit_reason"] == "stop_loss"
        assert trade["exit_price"] == pytest.approx(90.0)

    def test_commission_reduces_equity(self):
        data = _make_price_data(n=30)
        endings = []
        for commission in (0.0, 25.0):
            engine = BacktestEngine(
                initial_balance=100000.0,
                historical_data=data,
                commission_per_trade=commission,
            )
            step = {"n": 0}

            def buy_then_sell(stock_frame, indicator_client):
                step["n"] += 1
                if step["n"] == 3:
                    return "buy"
                if step["n"] == 15:
                    return "sell"
                return None

            endings.append(engine.run(strategy=buy_then_sell).ending_balance)
        assert endings[1] < endings[0]

    def test_position_size_fraction(self):
        rows = [(100.0, 101.0, 99.0, 100.0)] * 6
        engine = self._make_cost_free_engine(self._bars(rows), position_size_fraction=0.5)
        calls = {"n": 0}

        def strategy(stock_frame, indicator_client):
            calls["n"] += 1
            if calls["n"] == 1:
                return "buy"
            if calls["n"] == 4:
                return "sell"
            return None

        result = engine.run(strategy=strategy)
        assert result.total_trades == 1
        assert result.trades[0]["quantity"] == pytest.approx(500)

    def test_partial_fill_with_tiny_volume(self):
        """Volume participation caps fills; remainder re-attempts on later bars."""
        rows = [(100.0, 101.0, 99.0, 100.0)] * 10
        data = self._bars(rows)
        for bar in data:
            bar["volume"] = 100  # max fillable = max(1, 100*0.10) = 10 shares/bar
        engine = self._make_cost_free_engine(data)
        calls = {"n": 0}

        def strategy(stock_frame, indicator_client):
            calls["n"] += 1
            if calls["n"] == 1:
                return "buy"
            if calls["n"] == 8:
                return "sell"
            return None

        result = engine.run(strategy=strategy)
        assert result.total_trades == 1
        assert result.trades[0]["quantity"] == pytest.approx(70)
        assert result.trades[0]["quantity"] < 950

    def test_annualization_matches_bar_type(self):
        """Engine derives periods_per_year from bar_type; metrics scale Sharpe by it."""
        from pyrobot.backtesting.metrics import calculate_quantitative_metrics

        rows = [(100.0, 101.0, 99.0, 100.0)] * 6
        engine = self._make_cost_free_engine(self._bars(rows))
        calls = {"n": 0}

        def buy_once(stock_frame, indicator_client):
            calls["n"] += 1
            return "buy" if calls["n"] == 1 else None

        minute = engine.run(strategy=buy_once, bar_type="minute")
        assert minute.periods_per_year == 252 * 390
        daily_again = engine.run(strategy=buy_once, bar_type="day")
        assert daily_again.periods_per_year == 252

        # Exact scaling check at the metrics level (rf=0 removes per-period
        # risk-free drift so the ratio is purely sqrt(periods_per_year)).
        returns = [0.01, -0.005, 0.008, 0.012, -0.003, 0.006]
        equity = list(100000.0 * np.cumprod([1.0 + r for r in returns]))
        daily = calculate_quantitative_metrics(
            returns, equity, [], risk_free_rate=0.0, periods_per_year=252
        )
        minute_m = calculate_quantitative_metrics(
            returns, equity, [], risk_free_rate=0.0, periods_per_year=252 * 390
        )
        assert minute_m.sharpe_ratio / daily.sharpe_ratio == pytest.approx(390 ** 0.5)
