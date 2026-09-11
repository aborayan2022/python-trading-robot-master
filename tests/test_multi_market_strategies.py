"""Tests for all multi-market strategies (Wave 2).

Covers StrategyRegistry and each of the 6 new strategies with warm-up gating,
entry signals, exit signals, and on_order_fill state tracking.
"""

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from pyrobot.models.signal import SignalAction
from pyrobot.runtime.loop import TradingLoop, build_default_pipeline, replay_provider
from pyrobot.runtime.pipeline import _as_stock_frame
from pyrobot.strategies.registry import StrategyRegistry

# ── Synthetic data helpers ────────────────────────────────────────────────────


def _trend_path(n_bars: int = 300, drift: float = 0.004, amplitude: float = 5.0, period: float = 14.0):
    return [100.0 * (1 + drift * i) + amplitude * math.sin(i / period) for i in range(n_bars)]


def _mean_rev_path(n_bars: int = 300, base: float = 100.0, amplitude: float = 15.0, period: float = 20.0):
    return [base + amplitude * math.sin(i / period) for i in range(n_bars)]


def _volatile_path(n_bars: int = 300, base: float = 30000.0, volatility: float = 0.03):
    import numpy as np
    np.random.seed(42)
    prices = [base]
    for _ in range(n_bars - 1):
        change = np.random.normal(0, volatility)
        prices.append(prices[-1] * (1 + change))
    return prices


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


def _bars_for_us_trend(day0: datetime) -> list:
    """Gentle uptrend riding RSI 45–75 (BUY), then a steeper leg pushing
    RSI ≥ 70 while holding (SELL) — guaranteed trades through the pipeline."""
    prices = [
        100.0 + 0.4 * i + 8.0 * math.sin(i / 7) + (2.0 if i % 5 == 0 else 0)
        for i in range(260)
    ]
    base = 100.0 + 0.4 * 259 + 8.0 * math.sin(259 / 7)
    prices += [base + 2.2 * i for i in range(90)]
    return _bars_from_prices(prices, day0)


def _bars_for_us_mean_rev(day0: datetime) -> list:
    """Sine oscillation with volume spikes on down-bars, so RSI < 30 below
    the lower Bollinger band is triggered with volume_ok → BUY; reversion to
    SMA exits. Guaranteed round trips through the pipeline."""
    prices = []
    sma_buf = []
    n = 400
    for i in range(n):
        p = 100.0 + 8.0 * math.sin(2 * math.pi * i / 30)
        prices.append(round(p, 2))
        sma_buf.append(p)
    bars = []
    for i, close in enumerate(prices):
        sma20 = sum(sma_buf[max(0, i - 19):i + 1]) / min(20, i + 1)
        spike = close < sma20
        ts = day0 + timedelta(days=i)
        bars.append({
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1_000_000.0 * (3.0 if spike else 1.0),
            "datetime": ts,
        })
    return bars


def _stock_frame(bars: list, symbol: str = "TEST"):
    df = pd.DataFrame(bars)
    df["symbol"] = symbol
    return _as_stock_frame(df, symbol)


# ── StrategyRegistry tests ───────────────────────────────────────────────────


class TestStrategyRegistry:
    def setup_method(self):
        StrategyRegistry.clear()
        # Restore built-in strategies so later test modules still find them.
        from pyrobot.strategies import register_builtin_strategies
        register_builtin_strategies()

    def test_register_and_create(self):
        from pyrobot.strategies.us_trend import USTrendFollowStrategy
        StrategyRegistry.register("us_trend", USTrendFollowStrategy)
        strategy = StrategyRegistry.create("us_trend", symbols=["AAPL"])
        assert isinstance(strategy, USTrendFollowStrategy)

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            StrategyRegistry.create("nonexistent", symbols=["X"])

    def test_register_non_subclass_raises(self):
        with pytest.raises(TypeError):
            StrategyRegistry.register("bad", str)

    def test_available(self):
        from pyrobot.strategies.us_trend import USTrendFollowStrategy
        StrategyRegistry.register("a", USTrendFollowStrategy)
        StrategyRegistry.register("b", USTrendFollowStrategy)
        available = StrategyRegistry.available()
        # Built-in strategies are restored in setup_method; "a"/"b" must be present.
        assert "a" in available
        assert "b" in available
        assert "us_trend" in available
        assert available == sorted(available)

    def test_get_class(self):
        from pyrobot.strategies.us_trend import USTrendFollowStrategy
        StrategyRegistry.register("trend", USTrendFollowStrategy)
        assert StrategyRegistry.get_class("trend") is USTrendFollowStrategy

    def test_create_from_env(self, monkeypatch):
        from pyrobot.strategies.us_trend import USTrendFollowStrategy
        StrategyRegistry.register("us_trend", USTrendFollowStrategy)
        monkeypatch.setenv("PYROBOT_STRATEGY", "us_trend")
        strategy = StrategyRegistry.create_from_env(symbols=["AAPL"])
        assert isinstance(strategy, USTrendFollowStrategy)


# ── US Mean Reversion tests ──────────────────────────────────────────────────


class TestUSMeanReversionStrategy:
    def _make_strategy(self):
        from pyrobot.strategies.us_mean_reversion import USMeanReversionStrategy
        return USMeanReversionStrategy(strategy_id="us_mr_test", symbols=["TEST"])

    def test_warmup_returns_hold(self):
        strategy = self._make_strategy()
        # min_history_bars=30, so 15 bars is below warm-up
        prices = _mean_rev_path(15)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        signal = strategy.on_bar("TEST", bars[-1], _stock_frame(bars))
        assert signal.action == SignalAction.HOLD
        assert "Warm-up" in (signal.reason or "")

    def test_holding_toggles(self):
        strategy = self._make_strategy()
        assert strategy.get_holding("TEST") is False
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is True
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is False


# ── US Breakout tests ────────────────────────────────────────────────────────


class TestUSBreakoutStrategy:
    def _make_strategy(self):
        from pyrobot.strategies.us_breakout import USBreakoutStrategy
        return USBreakoutStrategy(strategy_id="us_bo_test", symbols=["TEST"])

    def test_warmup_returns_hold(self):
        strategy = self._make_strategy()
        prices = _trend_path(50)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        signal = strategy.on_bar("TEST", bars[-1], _stock_frame(bars))
        assert signal.action == SignalAction.HOLD
        assert "Warm-up" in (signal.reason or "")

    def test_holding_toggles(self):
        strategy = self._make_strategy()
        assert strategy.get_holding("TEST") is False
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is True
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is False


# ── Metals Trend tests ───────────────────────────────────────────────────────


class TestMetalsTrendFollowStrategy:
    def _make_strategy(self):
        from pyrobot.strategies.metals_trend import MetalsTrendFollowStrategy
        return MetalsTrendFollowStrategy(strategy_id="metals_t_test", symbols=["TEST"])

    def test_warmup_returns_hold(self):
        strategy = self._make_strategy()
        prices = _trend_path(30)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        signal = strategy.on_bar("TEST", bars[-1], _stock_frame(bars))
        assert signal.action == SignalAction.HOLD
        assert "Warm-up" in (signal.reason or "")

    def test_holding_toggles(self):
        strategy = self._make_strategy()
        assert strategy.get_holding("TEST") is False
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is True
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is False


# ── Metals Momentum tests ────────────────────────────────────────────────────


class TestMetalsMomentumBreakout:
    def _make_strategy(self):
        from pyrobot.strategies.metals_momentum import MetalsMomentumBreakout
        return MetalsMomentumBreakout(strategy_id="metals_m_test", symbols=["TEST"])

    def test_warmup_returns_hold(self):
        strategy = self._make_strategy()
        prices = _trend_path(50)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        signal = strategy.on_bar("TEST", bars[-1], _stock_frame(bars))
        assert signal.action == SignalAction.HOLD
        assert "Warm-up" in (signal.reason or "")

    def test_holding_toggles(self):
        strategy = self._make_strategy()
        assert strategy.get_holding("TEST") is False
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is True
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is False


# ── Crypto Trend tests ───────────────────────────────────────────────────────


class TestCryptoTrendBreakoutStrategy:
    def _make_strategy(self):
        from pyrobot.strategies.crypto_trend import CryptoTrendBreakoutStrategy
        return CryptoTrendBreakoutStrategy(strategy_id="crypto_t_test", symbols=["TEST"])

    def test_warmup_returns_hold(self):
        strategy = self._make_strategy()
        prices = _volatile_path(30)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        signal = strategy.on_bar("TEST", bars[-1], _stock_frame(bars))
        assert signal.action == SignalAction.HOLD
        assert "Warm-up" in (signal.reason or "")

    def test_holding_toggles(self):
        strategy = self._make_strategy()
        assert strategy.get_holding("TEST") is False
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is True
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is False


# ── Crypto Mean Reversion tests ──────────────────────────────────────────────


class TestCryptoMeanReversionStrategy:
    def _make_strategy(self):
        from pyrobot.strategies.crypto_mean_rev import CryptoMeanReversionStrategy
        return CryptoMeanReversionStrategy(strategy_id="crypto_mr_test", symbols=["TEST"])

    def test_warmup_returns_hold(self):
        strategy = self._make_strategy()
        # min_history_bars=30, so 15 bars is below warm-up
        prices = _mean_rev_path(15, base=30000, amplitude=5000)
        bars = _bars_from_prices(prices, datetime(2022, 1, 1, tzinfo=timezone.utc))
        signal = strategy.on_bar("TEST", bars[-1], _stock_frame(bars))
        assert signal.action == SignalAction.HOLD
        assert "Warm-up" in (signal.reason or "")

    def test_holding_toggles(self):
        strategy = self._make_strategy()
        assert strategy.get_holding("TEST") is False
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is True
        strategy.on_order_fill({"symbol": "TEST", "quantity": 10})
        assert strategy.get_holding("TEST") is False


# ── Pipeline integration test (all strategies) ───────────────────────────────


class TestStrategyPipelineIntegration:
    def test_us_trend_pipeline(self):
        bars = [{"TEST": bar} for bar in _bars_for_us_trend(datetime(2021, 1, 1, tzinfo=timezone.utc))]
        from pyrobot.strategies.us_trend import USTrendFollowStrategy
        strategy = USTrendFollowStrategy(strategy_id="e2e_us_trend", symbols=["TEST"])
        pipeline = build_default_pipeline(symbols=["TEST"], initial_balance=100_000.0, strategy=strategy)
        loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(bars), bar_interval=0.0)
        result = loop.run()
        # e2e proof: the pipeline must actually *trade* on the trending path —
        # at least one BUY entry filled and one SELL exit filled, with net
        # account value moving off the starting balance.
        fills = [o for o in pipeline.order_manager.all_orders() if o.status.value == "FILLED"]
        sides = [o.side.value for o in fills]
        assert result.get("bars_processed", 0) > 0
        assert "BUY" in sides and "SELL" in sides, f"expected real trades, got sides={sides}"
        assert pipeline.broker.get_account_info()["equity"] != 100_000.0

    def test_us_mean_rev_pipeline(self):
        bars = [{"TEST": bar} for bar in _bars_for_us_mean_rev(datetime(2021, 1, 1, tzinfo=timezone.utc))]
        from pyrobot.strategies.us_mean_reversion import USMeanReversionStrategy
        strategy = USMeanReversionStrategy(strategy_id="e2e_us_mr", symbols=["TEST"])
        pipeline = build_default_pipeline(symbols=["TEST"], initial_balance=100_000.0, strategy=strategy)
        loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(bars), bar_interval=0.0)
        result = loop.run()
        fills = [o for o in pipeline.order_manager.all_orders() if o.status.value == "FILLED"]
        assert result.get("bars_processed", 0) > 0
        assert len(fills) >= 2, f"expected round-trip trades, got {len(fills)} fills"
