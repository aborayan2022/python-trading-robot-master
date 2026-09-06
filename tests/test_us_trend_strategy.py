"""Tests for the US trend-follow strategy (pyrobot/strategies/us_trend.py).

Covers warm-up gating, BUY entry rules, SELL exit rules, and an end-to-end
run through the real TradingPipeline (signals → fills → holding tracking).
"""

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from pyrobot.models.signal import SignalAction
from pyrobot.runtime.loop import (
    TradingLoop,
    build_default_pipeline,
    replay_provider,
)
from pyrobot.runtime.pipeline import _as_stock_frame
from pyrobot.strategies.us_trend import USTrendFollowStrategy


def _trend_path(n_bars: int = 420, drift: float = 0.004, amplitude: float = 7.0, period: float = 14.0):
    """Deterministic uptrend with cyclical pullbacks (RSI oscillates)."""
    return [
        50.0 * (1 + drift * i) + amplitude * math.sin(i / period)
        for i in range(n_bars)
    ]


def _bars_from_prices(prices, day0: datetime) -> list:
    bars = []
    for i, close in enumerate(prices):
        ts = day0 + timedelta(days=i)
        bars.append({
            "open": close * 0.998,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000.0,
            "datetime": ts,
        })
    return bars


def _stock_frame(bars: list, symbol: str = "AAPL"):
    df = pd.DataFrame(bars)
    df["symbol"] = symbol
    return _as_stock_frame(df, symbol)


@pytest.fixture
def strategy():
    return USTrendFollowStrategy(strategy_id="us_trend_test", symbols=["AAPL"])


class TestUSTrendStrategy:
    def test_warmup_returns_hold(self, strategy):
        prices = _trend_path(60)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        signal = strategy.on_bar("AAPL", bars[-1], _stock_frame(bars))
        assert signal.action == SignalAction.HOLD
        assert "Warm-up" in (signal.reason or "")

    def test_entry_buy_in_uptrend(self, strategy):
        prices = _trend_path(420)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        # The pullback-rich uptrend must produce at least one BUY confirmation on
        # some evaluation bar (strategy stays flat here, so entry logic is free to
        # fire whenever all conditions align).
        buys = 0
        for bar_index in range(280, 420):
            signal = strategy.on_bar(
                "AAPL", bars[bar_index], _stock_frame(bars[: bar_index + 1])
            )
            if signal.action == SignalAction.BUY:
                buys += 1
        assert buys > 0
        # A BUY must always carry a symbol and positive confidence.
        signal = strategy.on_bar(
            "AAPL", bars[350], _stock_frame(bars[:351])
        )
        if signal.action == SignalAction.BUY:
            assert signal.symbol == "AAPL"
            assert signal.confidence > 0

    def test_exit_sell_when_holding_and_trend_breaks(self, strategy):
        prices = _trend_path(420)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        # Simulate a position opened at the uptrend peak, then price plunges.
        strategy._holding["AAPL"] = True
        strategy._entry_high["AAPL"] = prices[150]

        crash = prices[150:] + [prices[-1] * 0.5] * 20
        crash_bars = list(bars[:150]) + [
            {
                "open": c * 0.998,
                "high": c * 1.01,
                "low": c * 0.99,
                "close": c,
                "volume": 1_000_000.0,
                "datetime": bars[150]["datetime"] + timedelta(days=i + 1),
            }
            for i, c in enumerate(crash[150:])
        ]
        signal = strategy.on_bar("AAPL", crash_bars[-1], _stock_frame(crash_bars))
        assert signal.action == SignalAction.SELL
        strategy.on_order_fill({"symbol": "AAPL", "quantity": 10})
        assert strategy.get_holding("AAPL") is False

    def test_on_order_fill_toggles_holding(self, strategy):
        assert strategy.get_holding("AAPL") is False
        strategy.on_order_fill({"symbol": "AAPL", "quantity": 10})
        assert strategy.get_holding("AAPL") is True
        strategy.on_order_fill({"symbol": "AAPL", "quantity": 10})
        assert strategy.get_holding("AAPL") is False

    def test_pipeline_end_to_end_buys_and_sells(self):
        prices = _trend_path(700)
        bars = [
            {"AAPL": bar}
            for bar in _bars_from_prices(prices, datetime(2021, 1, 1, tzinfo=timezone.utc))
        ]
        strategy = USTrendFollowStrategy(strategy_id="us_trend_e2e", symbols=["AAPL"])
        pipeline = build_default_pipeline(
            symbols=["AAPL"], initial_balance=100_000.0, strategy=strategy
        )
        loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(bars), bar_interval=0.0)
        loop.run()

        orders = pipeline.order_manager.all_orders()
        assert any(o.side.value == "BUY" for o in orders)
        assert any(o.side.value == "SELL" for o in orders)

        # Fills must have been confirmed and the strategy's state toggled.
        fills = [o for o in orders if o.status.value == "FILLED"]
        assert len(fills) >= 2
        assert strategy.get_holding("AAPL") is False
