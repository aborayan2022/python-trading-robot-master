"""Production-readiness tests for Alpaca data, safety locks, and monitoring."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.data.alpaca import AlpacaDataProvider, is_us_equity_session
from pyrobot.exceptions import StaleDataError
from pyrobot.execution.order_manager import OrderManager
from pyrobot.execution.reconciliation import AccountReconciler
from pyrobot.monitoring import RuntimeMetrics, build_daily_report
from pyrobot.risk.kill_switch import KillSwitch
from pyrobot.runtime.loop import TradingLoop, build_alpaca_pipeline
from pyrobot.runtime.pipeline import TradingPipeline
from pyrobot.strategies.base import BaseStrategy


class _NoTradeStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(strategy_id="none", symbols=["MSFT"])

    def initialize(self) -> None:
        return None

    def on_bar(self, symbol: str, bar: dict, stock_frame):
        from pyrobot.models.signal import Signal, SignalAction

        return Signal(symbol=symbol, action=SignalAction.NO_TRADE, strategy_id="none")

    def on_order_fill(self, order_dict: dict) -> None:
        return None


class _FakeAlpacaClient:
    def __init__(self, bars=None, quotes=None):
        self.bars = bars or {}
        self.quotes = quotes or {}

    def get_stock_bars(self, request):
        return self.bars

    def get_stock_latest_quote(self, request):
        return self.quotes


def test_alpaca_provider_normalizes_historical_bars_and_quotes():
    ts = datetime(2026, 1, 5, 14, 31, tzinfo=timezone.utc)
    provider = AlpacaDataProvider(api_key="k", secret_key="s")
    provider._client = _FakeAlpacaClient(
        bars={
            "MSFT": [
                SimpleNamespace(
                    timestamp=ts,
                    open=100,
                    high=101,
                    low=99,
                    close=100.5,
                    volume=12345,
                    vwap=100.2,
                )
            ]
        },
        quotes={
            "MSFT": SimpleNamespace(
                timestamp=ts,
                bid_price=100.0,
                ask_price=100.2,
                bid_size=10,
                ask_size=12,
            )
        },
    )

    candles = provider.get_historical_candles("msft", ts - timedelta(minutes=1), ts)
    quote = provider.get_latest_quote("msft")

    assert candles[0].symbol == "MSFT"
    assert candles[0].timestamp.tzinfo is not None
    assert candles[0].close == 100.5
    assert quote.symbol == "MSFT"
    assert quote.last_price == pytest.approx(100.1)


def test_alpaca_polling_raises_stale_when_market_closed():
    provider = AlpacaDataProvider(api_key="k", secret_key="s")
    saturday = datetime(2026, 1, 3, 15, 0, tzinfo=timezone.utc)

    assert is_us_equity_session(saturday) is False
    with pytest.raises(StaleDataError):
        provider.poll_latest_bars(["MSFT"], now=saturday, require_market_session=True)


def test_live_profile_is_locked_without_explicit_flag(monkeypatch):
    monkeypatch.delenv("PYROBOT_ALLOW_LIVE_TRADING", raising=False)

    with pytest.raises(RuntimeError, match="Live Alpaca trading is locked"):
        build_alpaca_pipeline(["MSFT"], profile="alpaca_live_locked")


def test_loop_halts_on_stale_data_and_records_kill_switch():
    broker = PaperBroker(initial_balance=100_000)
    ledger = AuditLedger()
    pipeline = TradingPipeline(
        broker=broker,
        symbols=["MSFT"],
        signal_source=_NoTradeStrategy(),
        audit_ledger=ledger,
        min_history_bars=5,
    )

    def stale_provider(_index):
        raise StaleDataError("feed stopped")

    result = TradingLoop(pipeline, stale_provider).run()

    assert result["bars_processed"] == 0
    assert pipeline.kill_switch.is_active is True
    assert AuditAction.KILL_SWITCH_TRIGGERED in {e.action for e in ledger.get_events()}


def test_account_reconciler_halts_on_position_mismatch():
    broker = PaperBroker(initial_balance=100_000)
    broker.update_prices({"MSFT": {"last_price": 100, "close": 100, "open": 100, "high": 100, "low": 100}})
    ledger = AuditLedger()
    kill_switch = KillSwitch()

    reconciler = AccountReconciler(
        broker=broker,
        order_manager=OrderManager(),
        audit_ledger=ledger,
        kill_switch=kill_switch,
    )
    report = reconciler.reconcile(expected_positions={"MSFT": 10.0})

    assert report["ok"] is False
    assert kill_switch.is_active is True
    assert AuditAction.RECONCILIATION_RUN in {e.action for e in ledger.get_events()}


def test_runtime_metrics_and_daily_report(tmp_path):
    metrics = RuntimeMetrics(output_path=tmp_path / "metrics.jsonl")
    snap = metrics.record_snapshot(
        {"timestamp": "2026-01-05T14:30:00+00:00", "equity": 100_000, "orders": []},
        {"model_risk_scale": 1.0, "open_orders": 0},
    )
    ledger = AuditLedger(log_path=tmp_path / "audit.jsonl")
    ledger.record(AuditAction.ORDER_SUBMITTED, details={"x": 1})
    report = build_daily_report(ledger, output_path=tmp_path / "daily.json")

    assert snap["drawdown"] == 0.0
    assert (tmp_path / "metrics.jsonl").exists()
    assert report["orders_submitted"] == 1
    assert report["ledger_integrity"] is True
