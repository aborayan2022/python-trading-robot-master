"""Tests for the real-market live-session platform fixes.

Covers (each fix ships with a test):
  - 3.1.2: GICS sector map wired into the Alpaca paper pipeline
  - 3.1.3: TradingPipeline.seed_history() warms history without signals/orders
  - 3.1.4: USTrendFollowStrategy.sync_positions() cross-session state
  - 3.1.5: risk-rejected orders are marked REJECTED (not left NEW)
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from pyrobot.data.sectors import (
    US_EQUITY_GICS_SECTORS,
    build_sector_map,
    gics_sector,
)
from pyrobot.exceptions import ExecutionError
from pyrobot.models.order import OrderSide, OrderState
from pyrobot.models.signal import SignalAction
from pyrobot.risk.exposure import ExposureMonitor
from pyrobot.risk.limits import RiskLimits
from pyrobot.strategies.us_trend import USTrendFollowStrategy


# ── 3.1.2 Sector map ────────────────────────────────────────────────────────

class TestSectorMap:
    def test_all_ten_universe_symbols_classified(self):
        for symbol in ("AAPL", "AMZN", "GOOGL", "JNJ", "JPM", "META", "MSFT", "NVDA", "WMT", "XOM"):
            assert gics_sector(symbol) != "UNKNOWN"
            assert gics_sector(symbol) in US_EQUITY_GICS_SECTORS.values()

    def test_unknown_symbol_falls_back_to_unknown(self):
        assert gics_sector("ABCD123") == "UNKNOWN"

    def test_build_sector_map_covers_universe(self):
        sector_map = build_sector_map(["AAPL", "JNJ", "XYZ"])
        assert sector_map["AAPL"] == "Information Technology"
        assert sector_map["JNJ"] == "Health Care"
        assert sector_map["XYZ"] == "UNKNOWN"

    def test_exposure_buckets_by_gics_sector(self):
        limits = RiskLimits(
            max_position_size_pct=0.5,
            max_long_exposure_pct=1.5,
            max_portfolio_exposure_pct=1.5,
            max_sector_concentration_pct=0.25,
        )
        monitor = ExposureMonitor(limits=limits, sector_map=US_EQUITY_GICS_SECTORS)

        # AAPL + MSFT both bucket under "Information Technology" (not UNKNOWN).
        exposure = monitor.calculate_exposure(
            positions={"AAPL": 100, "MSFT": 100},
            prices={"AAPL": 200.0, "MSFT": 200.0},
            account_equity=100_000.0,
        )
        assert exposure.sector_exposure["Information Technology"] == 40_000.0
        assert "UNKNOWN" not in exposure.sector_exposure

        # Third IT name is capped by the real sector concentration limit.
        ok, reason = monitor.check_order(
            exposure, "NVDA", "BUY", 100, 200.0, 100_000.0,
            positions={"AAPL": 100, "MSFT": 100},
        )
        assert not ok
        assert "Sector 'Information Technology'" in reason

        # A different sector is NOT capped by the IT bucket.
        exposure_single = monitor.calculate_exposure(
            positions={"AAPL": 100}, prices={"AAPL": 200.0}, account_equity=100_000.0
        )
        ok2, _ = monitor.check_order(
            exposure_single, "JNJ", "BUY", 100, 150.0, 100_000.0,
            positions={"AAPL": 100},
        )
        assert ok2

    def test_build_alpaca_pipeline_wires_sector_map(self, monkeypatch):
        from pyrobot.brokers.paper_broker import PaperBroker
        from pyrobot.runtime import loop as loop_module

        def _stub_alpaca_broker(paper: bool = True):
            broker = PaperBroker(initial_balance=100_000.0)
            broker.authenticate()
            return broker

        monkeypatch.setattr(loop_module, "AlpacaBroker", _stub_alpaca_broker)
        pipeline = loop_module.build_alpaca_pipeline(
            symbols=["AAPL", "JNJ"], profile="alpaca_paper"
        )
        sector_map = pipeline.risk_manager.exposure_monitor._sector_map
        assert sector_map.get("AAPL") == "Information Technology"
        assert sector_map.get("JNJ") == "Health Care"


# ── 3.1.3 History seeding ───────────────────────────────────────────────────

def _daily_bars(n_bars: int = 420, drift: float = 0.004, start: datetime | None = None):
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(n_bars):
        close = 50.0 * (1 + drift * i) + 5.0 * math.sin(i / 7.0)
        bars.append({
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": round(close, 2),
            "volume": 1_000_000.0,
            "datetime": start + timedelta(days=i),
        })
    return bars


class TestSeedHistory:
    def test_seed_populates_history_without_signals_or_orders(self):
        from pyrobot.runtime.loop import build_default_pipeline

        strategy = USTrendFollowStrategy(strategy_id="seed_test", symbols=["AAPL"])
        pipeline = build_default_pipeline(symbols=["AAPL"], strategy=strategy)
        bars = _daily_bars(300)

        counts = pipeline.seed_history({"AAPL": bars})

        assert counts["AAPL"] == 300
        assert len(pipeline._history["AAPL"]) == 300
        assert pipeline._bars_processed == 0
        assert pipeline.order_manager.all_orders() == []

    def test_seed_history_accepts_candle_objects(self):
        from pyrobot.runtime.loop import build_default_pipeline

        bars = _daily_bars(300)
        candles = [
            _candle_from_bar(bar) for bar in bars
        ]
        pipeline = build_default_pipeline(symbols=["AAPL"])
        pipeline.seed_history({"AAPL": candles})
        assert len(pipeline._history["AAPL"]) == 300
        assert "datetime" in pipeline._history["AAPL"][0]

    def test_seeded_history_enables_signal_on_first_bar(self):
        from pyrobot.runtime.loop import build_default_pipeline

        strategy = USTrendFollowStrategy(strategy_id="seed_e2e", symbols=["AAPL"])
        pipeline = build_default_pipeline(symbols=["AAPL"], strategy=strategy)
        pipeline.seed_history({"AAPL": _daily_bars(300)})

        last = pipeline._history["AAPL"][-1]
        result = pipeline.process_bar({"AAPL": last})
        signals = result["signals"]

        assert len(signals) == 1
        # Warm-up gate passed — the strategy evaluated a real bar.
        assert "Warm-up" not in (signals[0].get("reason") or "")


def _candle_from_bar(bar):
    from pyrobot.data.base import Candle

    return Candle(
        symbol="AAPL",
        timestamp=bar["datetime"],
        open=bar["open"],
        high=bar["high"],
        low=bar["low"],
        close=bar["close"],
        volume=bar["volume"],
    )


# ── 3.1.4 Position synchronization ──────────────────────────────────────────

class TestSyncPositions:
    def test_sync_positions_toggles_holding(self):
        strategy = USTrendFollowStrategy(strategy_id="sync_test", symbols=["AAPL", "MSFT"])
        assert strategy.get_holding("AAPL") is False

        strategy.sync_positions({"AAPL": 10.0})
        assert strategy.get_holding("AAPL") is True
        assert strategy.get_symbol_state("AAPL").get("holding") is True

        strategy.sync_positions({"AAPL": 0.0, "MSFT": 5.0})
        assert strategy.get_holding("AAPL") is False
        assert strategy.get_holding("MSFT") is True

    def test_sync_positions_long_only_ignores_shorts(self):
        strategy = USTrendFollowStrategy(strategy_id="sync_short", symbols=["AAPL"])
        strategy.sync_positions({"AAPL": -100.0})
        assert strategy.get_holding("AAPL") is False

    def test_sync_positions_clears_trailing_state_on_exit(self):
        strategy = USTrendFollowStrategy(strategy_id="sync_trail", symbols=["AAPL"])
        strategy._holding["AAPL"] = True
        strategy._entry_high["AAPL"] = 200.0
        strategy.sync_positions({"AAPL": 0.0})
        assert strategy.get_holding("AAPL") is False
        assert "AAPL" not in strategy._entry_high


# ── 3.1.5 Risk-rejected orders ──────────────────────────────────────────────

class TestRiskRejectedOrdersTerminal:
    def _engine_with_failing_risk(self):
        from pyrobot.brokers.paper_broker import PaperBroker
        from pyrobot.execution.engine import ExecutionEngine
        from pyrobot.execution.order_manager import OrderManager
        from pyrobot.risk.kill_switch import KillSwitch
        from pyrobot.risk.manager import RiskManager

        broker = PaperBroker(initial_balance=100_000.0)
        broker.authenticate()
        kill_switch = KillSwitch()
        order_manager = OrderManager()
        risk_manager = RiskManager(kill_switch=kill_switch, limits=RiskLimits())
        engine = ExecutionEngine(
            broker=broker,
            order_manager=order_manager,
            kill_switch=kill_switch,
            risk_manager=risk_manager,
        )
        # Tiny equity vs huge market order → gross-exposure rejection.
        engine.set_risk_context(positions={}, prices={"MSFT": 200.0}, equity=1_000.0)
        return engine, order_manager

    def test_risk_rejected_order_is_marked_rejected(self):
        engine, order_manager = self._engine_with_failing_risk()
        order = order_manager.create(symbol="MSFT", side=OrderSide.BUY, quantity=100)

        with pytest.raises(ExecutionError):
            engine.submit(order)

        assert order.status is OrderState.REJECTED
        assert order not in order_manager.active_orders()

    def test_fail_closed_rejection_remains_rejected(self):
        # No price in the risk context → fail-closed rejection path.
        from pyrobot.brokers.paper_broker import PaperBroker
        from pyrobot.execution.engine import ExecutionEngine
        from pyrobot.execution.order_manager import OrderManager
        from pyrobot.risk.kill_switch import KillSwitch

        broker = PaperBroker(initial_balance=100_000.0)
        broker.authenticate()
        kill_switch = KillSwitch()
        order_manager = OrderManager()
        engine = ExecutionEngine(
            broker=broker,
            order_manager=order_manager,
            kill_switch=kill_switch,
        )
        engine.set_risk_context(positions={}, prices={}, equity=100_000.0)
        order = order_manager.create(symbol="MSFT", side=OrderSide.BUY, quantity=10)

        with pytest.raises(ExecutionError):
            engine.submit(order)

        assert order.status is OrderState.REJECTED