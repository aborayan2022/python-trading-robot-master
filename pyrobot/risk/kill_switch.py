"""Kill Switch — hard stop for all trading activity.

The KillSwitch is a safety mechanism that immediately halts all new order
submissions when triggered.  It is the last line of defence against:

    - Daily loss limit breaches
    - Maximum drawdown breaches
    - Stale / missing data feeds
    - Broker connection failures
    - Unexpected position mismatches
    - Repeated order failures
    - Model service failures
    - Abnormal market conditions
    - Manual operator intervention

Once activated, no orders may pass through the Execution Engine until the
switch is explicitly reset by an authorised operator.

Usage::

    ks = KillSwitch()

    # Anywhere in the system:
    if daily_loss > max_daily_loss:
        ks.activate(KillSwitchReason.DAILY_LOSS_LIMIT, detail=f"Loss={daily_loss}")

    # Before submitting any order:
    ks.guard()   # raises KillSwitchError if active

    # Operator reset (requires explicit confirmation):
    ks.reset(confirmed=True)
"""

import threading

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pyrobot.exceptions import KillSwitchError
from pyrobot.logging_config import get_logger

logger = get_logger("kill_switch")


class KillSwitchReason(str, Enum):
    """Enumeration of all valid kill-switch activation reasons."""

    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    DATA_FEED_STALE = "DATA_FEED_STALE"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    REPEATED_ORDER_FAILURES = "REPEATED_ORDER_FAILURES"
    MODEL_SERVICE_FAILURE = "MODEL_SERVICE_FAILURE"
    ABNORMAL_MARKET = "ABNORMAL_MARKET"
    SYSTEM_HEALTH_FAILURE = "SYSTEM_HEALTH_FAILURE"
    OPERATOR = "OPERATOR"  # Manual activation by a human operator


class KillSwitchEvent:
    """Immutable record of a single kill-switch activation."""

    __slots__ = ("reason", "detail", "activated_at")

    def __init__(self, reason: KillSwitchReason, detail: str = "") -> None:
        self.reason: KillSwitchReason = reason
        self.detail: str = detail
        self.activated_at: datetime = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return (
            f"KillSwitchEvent(reason={self.reason.value!r}, "
            f"detail={self.detail!r}, activated_at={self.activated_at.isoformat()!r})"
        )


class KillSwitch:
    """Thread-safe kill switch for the trading platform.

    All state mutations are protected by an internal :class:`threading.Lock`
    so the switch can safely be activated from concurrent threads (e.g. a
    monitoring thread and the main trading loop).

    Attributes:
        is_active: True when the kill switch has been activated.
        activation_history: Ordered list of all activation events (never cleared
            on reset — provides a permanent audit trail).
    """

    def __init__(self) -> None:
        self._active: bool = False
        self._current_event: Optional[KillSwitchEvent] = None
        self._history: List[KillSwitchEvent] = []
        self._lock = threading.Lock()

    # ── State queries ─────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """Return True if the kill switch is currently active."""
        with self._lock:
            return self._active

    @property
    def current_event(self) -> Optional[KillSwitchEvent]:
        """Return the event that activated the switch, or None if inactive."""
        with self._lock:
            return self._current_event

    @property
    def activation_history(self) -> List[KillSwitchEvent]:
        """Return a snapshot of all historical activation events."""
        with self._lock:
            return list(self._history)

    # ── Activation ────────────────────────────────────────────────────────────

    def activate(
        self,
        reason: KillSwitchReason,
        detail: str = "",
    ) -> None:
        """Activate the kill switch.

        If the switch is already active the call is idempotent — the reason
        and detail of the *original* activation are preserved, but the new
        event is still recorded in the history for auditing.

        Args:
            reason: The :class:`KillSwitchReason` that triggered activation.
            detail: Optional free-text detail (e.g. loss amount, position diff).
        """
        event = KillSwitchEvent(reason=reason, detail=detail)

        with self._lock:
            self._history.append(event)

            if not self._active:
                self._active = True
                self._current_event = event

                logger.critical(
                    "KILL SWITCH ACTIVATED — reason=%s detail=%r time=%s",
                    reason.value,
                    detail,
                    event.activated_at.isoformat(),
                )
            else:
                logger.warning(
                    "Kill switch already active. Additional trigger recorded — "
                    "reason=%s detail=%r",
                    reason.value,
                    detail,
                )

    # ── Guard ─────────────────────────────────────────────────────────────────

    def guard(self) -> None:
        """Assert that the kill switch is NOT active.

        Call this at the start of any order-submission path.

        Raises:
            KillSwitchError: If the kill switch is currently active.
        """
        with self._lock:
            if self._active and self._current_event is not None:
                raise KillSwitchError(
                    reason=(
                        f"{self._current_event.reason.value} — "
                        f"{self._current_event.detail}"
                    )
                )

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self, *, confirmed: bool = False) -> None:
        """Reset the kill switch.

        Requires explicit ``confirmed=True`` to prevent accidental resets.

        This should only be called by an authorised operator after root-cause
        analysis and remediation of the triggering condition.

        Args:
            confirmed: Must be ``True`` to perform the reset.

        Raises:
            ValueError: If ``confirmed`` is False.
        """
        if not confirmed:
            raise ValueError(
                "Kill switch reset requires confirmed=True. "
                "Ensure the triggering condition has been resolved before resetting."
            )

        with self._lock:
            previous_event = self._current_event
            self._active = False
            self._current_event = None

        logger.warning(
            "KILL SWITCH RESET by operator. Previous activation: %r",
            previous_event,
        )

    # ── Context manager support ───────────────────────────────────────────────

    def __repr__(self) -> str:
        state = "ACTIVE" if self._active else "INACTIVE"
        event_info = (
            f", reason={self._current_event.reason.value!r}"
            if self._current_event
            else ""
        )
        return f"KillSwitch(state={state}{event_info})"
