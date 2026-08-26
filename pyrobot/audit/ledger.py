"""Immutable Audit Ledger for complete traceability of all quantitative trading decisions."""

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyrobot.exceptions import PyRobotError


class AuditIntegrityError(PyRobotError):
    """Raised when the audit ledger's tamper-evident chain fails verification.

    This indicates the JSONL log file has been corrupted, truncated,
    reordered, or deliberately tampered with.  The ledger refuses to
    operate on a file that fails chain verification.
    """


class AuditAction(str, Enum):
    """Types of auditable actions in the platform."""

    MARKET_DATA_RECORDED = "MARKET_DATA_RECORDED"
    DATA_QUALITY_CHECK = "DATA_QUALITY_CHECK"
    FEATURE_EXTRACTED = "FEATURE_EXTRACTED"
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RISK_EVALUATED = "RISK_EVALUATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    KILL_SWITCH_TRIGGERED = "KILL_SWITCH_TRIGGERED"
    KILL_SWITCH_RESET = "KILL_SWITCH_RESET"
    RECONCILIATION_RUN = "RECONCILIATION_RUN"
    PORTFOLIO_SNAPSHOT = "PORTFOLIO_SNAPSHOT"
    MODEL_DRIFT_CHECK = "MODEL_DRIFT_CHECK"
    CONTROL_ACTION = "CONTROL_ACTION"


@dataclass
class AuditEvent:
    """Immutable record of an auditable event with cryptographic chaining.

    Attributes:
        event_id: Unique sequential or hash-based ID.
        action: Type of action.
        timestamp: UTC timestamp.
        symbol: Associated ticker symbol (if any).
        order_id: Associated client_order_id (if any).
        strategy_id: Strategy identifier (if any).
        model_id: Model identifier / version (if any).
        details: Payload of event-specific data.
        prev_checksum: Checksum of previous event in chain.
        checksum: SHA-256 hash of this event's content + prev_checksum.
    """

    event_id: int
    action: AuditAction
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    symbol: Optional[str] = None
    order_id: Optional[str] = None
    strategy_id: Optional[str] = None
    model_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    prev_checksum: str = "GENESIS"
    checksum: str = ""

    def calculate_checksum(self) -> str:
        """Calculate deterministic SHA256 checksum for audit immutability."""
        payload = {
            "event_id": self.event_id,
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "order_id": self.order_id,
            "strategy_id": self.strategy_id,
            "model_id": self.model_id,
            "details": self.details,
            "prev_checksum": self.prev_checksum,
        }
        raw_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize audit event to dictionary."""
        return {
            "event_id": self.event_id,
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "order_id": self.order_id,
            "strategy_id": self.strategy_id,
            "model_id": self.model_id,
            "details": self.details,
            "prev_checksum": self.prev_checksum,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEvent":
        """Rebuild an AuditEvent from its serialized dictionary form.

        Args:
            data: Dict as produced by :meth:`to_dict`.

        Returns:
            The reconstructed :class:`AuditEvent`.

        Raises:
            ValueError: If required fields are missing or the action /
                timestamp values cannot be parsed.
        """
        try:
            action = AuditAction(data["action"])
            timestamp = datetime.fromisoformat(str(data["timestamp"]))
        except KeyError as exc:
            raise ValueError(f"Audit event missing required field: {exc}") from exc
        except ValueError as exc:
            raise ValueError(f"Invalid audit event payload: {exc}") from exc

        return cls(
            event_id=int(data["event_id"]),
            action=action,
            timestamp=timestamp,
            symbol=data.get("symbol"),
            order_id=data.get("order_id"),
            strategy_id=data.get("strategy_id"),
            model_id=data.get("model_id"),
            details=dict(data.get("details") or {}),
            prev_checksum=str(data.get("prev_checksum", "GENESIS")),
            checksum=str(data.get("checksum", "")),
        )


class AuditLedger:
    """Thread-safe, append-only tamper-evident audit ledger.

    If ``log_path`` points to an existing JSONL file, the file is loaded
    on init and its hash chain is verified.  A corrupted or tampered file
    raises :class:`AuditIntegrityError` rather than silently starting a
    fresh chain, and event IDs continue from the loaded maximum so the
    append-only sequence is preserved across restarts.

    Args:
        log_path: Optional path to a JSONL persistence file.  Parent
            directories are created automatically.
        sync: If True, every :meth:`record` call fsyncs the file to disk
            after flushing (durable writes at the cost of throughput).
    """

    def __init__(self, log_path: Optional[Path | str] = None, sync: bool = False) -> None:
        self._log_path: Optional[Path] = Path(log_path) if log_path else None
        self._sync: bool = sync
        self._events: List[AuditEvent] = []
        self._last_checksum: str = "GENESIS"
        self._lock = threading.RLock()

        if self._log_path and self._log_path.parent:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            if self._log_path.exists():
                self._load_from_file()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load_from_file(self) -> None:
        """Load and verify the JSONL log file (caller holds no lock yet).

        Rebuilds :class:`AuditEvent` objects, verifies the hash chain,
        and resumes the sequence so new events chain onto the file.

        Raises:
            AuditIntegrityError: If the file is unreadable, malformed,
                or fails chain verification.
        """
        assert self._log_path is not None  # for type checkers
        events = self._read_file_events(self._log_path)

        if not self._verify_chain(events):
            raise AuditIntegrityError(
                f"Audit log integrity verification failed on load: "
                f"{self._log_path} — the file may have been tampered with."
            )

        self._events = events
        self._last_checksum = events[-1].checksum if events else "GENESIS"

    def _read_file_events(self, path: Path) -> List[AuditEvent]:
        """Read a JSONL audit file and rebuild its events.

        Raises:
            AuditIntegrityError: On unreadable or malformed lines.
        """
        events: List[AuditEvent] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_no, raw_line in enumerate(f, start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if not isinstance(data, dict):
                            raise ValueError("event line is not a JSON object")
                        events.append(AuditEvent.from_dict(data))
                    except (json.JSONDecodeError, ValueError, TypeError) as exc:
                        raise AuditIntegrityError(
                            f"Corrupt audit log line {line_no} in {path}: {exc}"
                        ) from exc
        except OSError as exc:
            raise AuditIntegrityError(f"Cannot read audit log {path}: {exc}") from exc
        return events

    @staticmethod
    def _verify_chain(events: List[AuditEvent]) -> bool:
        """Verify the hash chain of a sequence of events.

        Checks that ``prev_checksum`` links, per-event checksums, and the
        sequential 1..N event ID ordering are all intact.
        """
        prev = "GENESIS"
        for expected_id, event in enumerate(events, start=1):
            if event.event_id != expected_id:
                return False
            if event.prev_checksum != prev:
                return False
            if event.calculate_checksum() != event.checksum:
                return False
            prev = event.checksum
        return True

    def _append_to_file(self, event: AuditEvent) -> None:
        """Append an event to the JSONL file, flushing (and optionally fsyncing)."""
        if self._log_path is None:
            return
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), default=str) + "\n")
            f.flush()
            if self._sync:
                os.fsync(f.fileno())

    # ── Public API ─────────────────────────────────────────────────────────────

    def record(
        self,
        action: AuditAction,
        details: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> AuditEvent:
        """Append a new tamper-evident event to the ledger.

        The event is chained onto the last checksum (in memory and, when
        a log path is configured, on disk) and its ID continues the
        sequence of any previously persisted events.
        """
        with self._lock:
            event_id = self._events[-1].event_id + 1 if self._events else 1
            event = AuditEvent(
                event_id=event_id,
                action=action,
                timestamp=datetime.now(timezone.utc),
                symbol=symbol,
                order_id=order_id,
                strategy_id=strategy_id,
                model_id=model_id,
                details=details or {},
                prev_checksum=self._last_checksum,
            )
            event.checksum = event.calculate_checksum()
            self._last_checksum = event.checksum
            self._events.append(event)

            self._append_to_file(event)

            return event

    def get_events(
        self,
        action: Optional[AuditAction] = None,
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[AuditEvent]:
        """Query events matching filter criteria."""
        with self._lock:
            results = self._events
            if action is not None:
                results = [e for e in results if e.action == action]
            if symbol is not None:
                results = [e for e in results if e.symbol == symbol]
            if order_id is not None:
                results = [e for e in results if e.order_id == order_id]
            if limit is not None:
                results = results[-limit:]
            return list(results)

    def verify_integrity(self) -> bool:
        """Verify the cryptographic hash chain of all in-memory events."""
        with self._lock:
            return self._verify_chain(self._events)

    def verify_file_integrity(self) -> bool:
        """Read the JSONL log file from disk and verify its hash chain.

        Unlike :meth:`verify_integrity`, this checks what is actually
        persisted, detecting on-disk tampering that happened after the
        events were recorded.

        Returns:
            True if the file's chain is intact (or no file is configured),
            False if the file is missing, malformed, or tampered with.
        """
        with self._lock:
            if self._log_path is None:
                return True
            if not self._log_path.exists():
                return False
            try:
                events = self._read_file_events(self._log_path)
            except AuditIntegrityError:
                return False
            return self._verify_chain(events)

    @property
    def total_events(self) -> int:
        """Return count of all recorded events."""
        with self._lock:
            return len(self._events)

    @property
    def log_path(self) -> Optional[Path]:
        """Return the persistence file path, or None if in-memory only."""
        return self._log_path

    def clear(self) -> None:
        """Clear in-memory ledger (used primarily in test setups).

        Note: this does NOT delete the JSONL file if one is configured.
        """
        with self._lock:
            self._events.clear()
            self._last_checksum = "GENESIS"
