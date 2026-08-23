"""Unit tests for AuditLedger and cryptographic tamper-evidence."""

import json
from pathlib import Path

import pytest

from pyrobot.audit import AuditAction, AuditIntegrityError, AuditLedger


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


class TestAuditLedgerPersistence:
    """Persistence, reload, and on-disk tamper detection."""

    def _record_three_events(self, ledger: AuditLedger) -> None:
        ledger.record(
            action=AuditAction.SIGNAL_GENERATED,
            symbol="AAPL",
            details={"probability": 0.7},
            strategy_id="strat_1",
        )
        ledger.record(
            action=AuditAction.ORDER_SUBMITTED,
            symbol="AAPL",
            order_id="ord-1",
            details={"quantity": 10, "side": "BUY"},
        )
        ledger.record(
            action=AuditAction.ORDER_FILLED,
            symbol="AAPL",
            order_id="ord-1",
            details={"filled_quantity": 10, "avg_price": 150.0},
        )

    def test_persistence_round_trip(self, tmp_path: Path) -> None:
        log_file = tmp_path / "audit" / "ledger.jsonl"

        original = AuditLedger(log_path=log_file)
        self._record_three_events(original)
        assert original.total_events == 3
        assert original.verify_integrity() is True

        # New instance over the same file: events reload, chain intact.
        reopened = AuditLedger(log_path=log_file)
        assert reopened.total_events == 3
        assert reopened.verify_integrity() is True

        events = reopened.get_events()
        assert [e.event_id for e in events] == [1, 2, 3]
        assert [e.action for e in events] == [
            AuditAction.SIGNAL_GENERATED,
            AuditAction.ORDER_SUBMITTED,
            AuditAction.ORDER_FILLED,
        ]

        # IDs continue from the loaded max id and chain onto the last checksum.
        e4 = reopened.record(action=AuditAction.PORTFOLIO_SNAPSHOT, details={"eq": 1.0})
        assert e4.event_id == 4
        assert e4.prev_checksum == events[-1].checksum
        assert reopened.total_events == 4
        assert reopened.verify_integrity() is True

        # And the appended event is visible to yet another reload.
        third = AuditLedger(log_path=log_file)
        assert third.total_events == 4
        assert third.get_events()[-1].event_id == 4
        assert third.verify_integrity() is True

    def test_tampered_file_raises_on_init(self, tmp_path: Path) -> None:
        log_file = tmp_path / "ledger.jsonl"
        ledger = AuditLedger(log_path=log_file)
        self._record_three_events(ledger)

        # Tamper with the first event's payload on disk.
        lines = log_file.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace('"probability": 0.7', '"probability": 0.99')
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with pytest.raises(AuditIntegrityError):
            AuditLedger(log_path=log_file)

    def test_deleted_middle_line_raises_on_init(self, tmp_path: Path) -> None:
        log_file = tmp_path / "ledger.jsonl"
        ledger = AuditLedger(log_path=log_file)
        self._record_three_events(ledger)

        # Delete the middle line — event 3 then chains onto event 1's checksum.
        lines = log_file.read_text(encoding="utf-8").splitlines()
        log_file.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")

        with pytest.raises(AuditIntegrityError):
            AuditLedger(log_path=log_file)

    def test_verify_file_integrity_detects_tampering(self, tmp_path: Path) -> None:
        log_file = tmp_path / "ledger.jsonl"
        ledger = AuditLedger(log_path=log_file)
        self._record_three_events(ledger)

        assert ledger.verify_file_integrity() is True

        # Tamper with the second event's action on disk.
        lines = log_file.read_text(encoding="utf-8").splitlines()
        lines[1] = lines[1].replace('"ORDER_SUBMITTED"', '"ORDER_CANCELLED"')
        log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert ledger.verify_file_integrity() is False

    def test_verify_file_integrity_detects_corrupt_line(self, tmp_path: Path) -> None:
        log_file = tmp_path / "ledger.jsonl"
        ledger = AuditLedger(log_path=log_file)
        self._record_three_events(ledger)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write("this is not valid json\n")

        assert ledger.verify_file_integrity() is False

    def test_verify_file_integrity_no_file_configured(self) -> None:
        ledger = AuditLedger()
        ledger.record(AuditAction.SIGNAL_GENERATED, symbol="AAPL")
        # In-memory only ledger: nothing on disk to verify against.
        assert ledger.verify_file_integrity() is True

    def test_sync_writes_durable_lines(self, tmp_path: Path) -> None:
        log_file = tmp_path / "ledger-sync.jsonl"
        ledger = AuditLedger(log_path=log_file, sync=True)
        ledger.record(action=AuditAction.DATA_QUALITY_CHECK, details={"score": 0.9})

        on_disk = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(on_disk) == 1
        assert on_disk[0]["action"] == "DATA_QUALITY_CHECK"
