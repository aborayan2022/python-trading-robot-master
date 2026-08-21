"""Unit tests for AuditLedger and cryptographic tamper-evidence."""

import pytest
from datetime import datetime, timezone
from pyrobot.audit import AuditAction, AuditEvent, AuditLedger


class TestAuditLedger:
    """Test suite for AuditLedger."""

    def test_record_and_query_events(self) -> None:
        ledger = AuditLedger()
        assert ledger.total_events == 0

        e1 = ledger.record(
            action=AuditAction.SIGNAL_GENERATED,
            symbol="AAPL",
            details={"probability": 0.85, "confidence": 0.9},
            strategy_id="strat_1",
            model_id="xgb_v1",
        )
        assert ledger.total_events == 1
        assert e1.event_id == 1
        assert e1.action == AuditAction.SIGNAL_GENERATED
        assert e1.symbol == "AAPL"
        assert e1.prev_checksum == "GENESIS"
        assert len(e1.checksum) == 64

        e2 = ledger.record(
            action=AuditAction.ORDER_SUBMITTED,
            symbol="AAPL",
            order_id="ord_123",
            details={"quantity": 100, "side": "BUY"},
        )
        assert ledger.total_events == 2
        assert e2.event_id == 2
        assert e2.prev_checksum == e1.checksum
        assert len(e2.checksum) == 64

    def test_cryptographic_integrity_verification(self) -> None:
        ledger = AuditLedger()
        for i in range(5):
            ledger.record(
                action=AuditAction.MARKET_DATA_RECORDED,
                symbol="MSFT",
                details={"bar_index": i, "close": 300.0 + i},
            )

        assert ledger.verify_integrity() is True

        # Tamper with an event in memory
        events = ledger.get_events()
        events[2].details["close"] = 9999.0
        assert ledger.verify_integrity() is False

    def test_filter_queries(self) -> None:
        ledger = AuditLedger()
        ledger.record(AuditAction.SIGNAL_GENERATED, symbol="AAPL")
        ledger.record(AuditAction.ORDER_SUBMITTED, symbol="AAPL", order_id="o1")
        ledger.record(AuditAction.ORDER_FILLED, symbol="AAPL", order_id="o1")
        ledger.record(AuditAction.SIGNAL_GENERATED, symbol="NVDA")

        aapl_events = ledger.get_events(symbol="AAPL")
        assert len(aapl_events) == 3

        signal_events = ledger.get_events(action=AuditAction.SIGNAL_GENERATED)
        assert len(signal_events) == 2

        order_events = ledger.get_events(order_id="o1")
        assert len(order_events) == 2
