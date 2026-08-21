"""Immutable Audit Ledger for complete traceability of all quantitative trading decisions."""

import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


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


class AuditLedger:
    """Thread-safe, append-only tamper-evident audit ledger."""

    def __init__(self, log_path: Optional[Path | str] = None) -> None:
        self._log_path: Optional[Path] = Path(log_path) if log_path else None
        self._events: List[AuditEvent] = []
        self._last_checksum: str = "GENESIS"
        self._lock = threading.RLock()

        if self._log_path and self._log_path.parent:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        action: AuditAction,
        details: Optional[Dict[str, Any]] = None,
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> AuditEvent:
        """Append a new tamper-evident event to the ledger."""
        with self._lock:
            event_id = len(self._events) + 1
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

            if self._log_path:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict(), default=str) + "\n")

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
        """Verify the cryptographic hash chain of all recorded events."""
        with self._lock:
            prev = "GENESIS"
            for event in self._events:
                if event.prev_checksum != prev:
                    return False
                if event.calculate_checksum() != event.checksum:
                    return False
                prev = event.checksum
            return True

    @property
    def total_events(self) -> int:
        """Return count of all recorded events."""
        with self._lock:
            return len(self._events)

    def clear(self) -> None:
        """Clear in-memory ledger (used primarily in test setups)."""
        with self._lock:
            self._events.clear()
            self._last_checksum = "GENESIS"
