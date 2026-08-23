"""Drawdown Monitor — tracks portfolio drawdown and triggers protection.

Calculates running peak equity and current drawdown, triggering
kill-switch activation when configured thresholds are breached.

Usage::

    dd = DrawdownMonitor(limits=RiskLimits())

    # Feed equity updates
    dd.update(100_000.0)  # new equity
    dd.update(98_000.0)
    dd.update(95_000.0)

    if dd.is_breached:
        kill_switch.activate(KillSwitchReason.MAX_DRAWDOWN, detail=dd.status())
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from pyrobot.logging_config import get_logger
from pyrobot.risk.limits import RiskLimits

logger = get_logger("drawdown_monitor")


@dataclass
class DrawdownEvent:
    """Record of a drawdown threshold breach."""

    peak_equity: float
    trough_equity: float
    drawdown_pct: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DrawdownMonitor:
    """Monitors portfolio drawdown in real-time and triggers protection.

    Args:
        limits: RiskLimits configuration.
    """

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self._limits = limits or RiskLimits()
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._max_drawdown_reached: float = 0.0
        self._breach_events: List[DrawdownEvent] = []
        self._daily_start_equity: Optional[float] = None
        self._daily_date: Optional[str] = None

    def update(self, equity: float) -> None:
        """Update the monitor with current portfolio equity.

        Args:
            equity: Current total portfolio equity in dollars.
        """
        self._current_equity = equity

        if equity > self._peak_equity:
            self._peak_equity = equity

        if self._peak_equity > 0:
            current_dd = (self._peak_equity - equity) / self._peak_equity
            if current_dd > self._max_drawdown_reached:
                self._max_drawdown_reached = current_dd

    def set_daily_start(self, equity: float, date_str: str) -> None:
        """Record the equity at the start of a trading day.

        Args:
            equity: Portfolio equity at market open.
            date_str: Date string (e.g. "2024-01-15").
        """
        if self._daily_date != date_str:
            self._daily_start_equity = equity
            self._daily_date = date_str
            logger.info("Daily start equity set: $%.2f for %s", equity, date_str)

    @property
    def current_drawdown(self) -> float:
        """Current drawdown from peak (0.0 to 1.0)."""
        if self._peak_equity <= 0:
            return 0.0
        return (self._peak_equity - self._current_equity) / self._peak_equity

    @property
    def max_drawdown(self) -> float:
        """Maximum drawdown reached since inception (0.0 to 1.0)."""
        return self._max_drawdown_reached

    @property
    def is_breached(self) -> bool:
        """True if current drawdown exceeds the configured limit."""
        return self.current_drawdown >= self._limits.max_drawdown_pct

    @property
    def daily_loss_pct(self) -> float:
        """Today's loss as a fraction of daily start equity."""
        if self._daily_start_equity is None or self._daily_start_equity <= 0:
            return 0.0
        loss = self._daily_start_equity - self._current_equity
        if loss <= 0:
            return 0.0
        return loss / self._daily_start_equity

    @property
    def is_daily_breached(self) -> bool:
        """True if today's loss exceeds the daily loss limit."""
        return self.daily_loss_pct >= self._limits.max_daily_loss_pct

    def status(self) -> str:
        """Return a human-readable status string."""
        return (
            f"DD={self.current_drawdown:.2%} "
            f"(max={self._max_drawdown_reached:.2%}, "
            f"limit={self._limits.max_drawdown_pct:.2%}) "
            f"daily_loss={self.daily_loss_pct:.2%} "
            f"(limit={self._limits.max_daily_loss_pct:.2%})"
        )

    def reset_peak(self, new_peak: float | None = None) -> None:
        """Reset the peak equity (e.g. after operator intervention).

        Args:
            new_peak: New peak value. Defaults to current equity.
        """
        old_peak = self._peak_equity
        self._peak_equity = new_peak if new_peak is not None else self._current_equity
        logger.warning(
            "Drawdown peak reset: $%.2f → $%.2f", old_peak, self._peak_equity
        )

    def reset(self) -> None:
        """Full reset of all drawdown tracking state."""
        self._peak_equity = 0.0
        self._current_equity = 0.0
        self._max_drawdown_reached = 0.0
        self._breach_events = []
        self._daily_start_equity = None
        self._daily_date = None
        logger.warning("Drawdown monitor fully reset")

    def __repr__(self) -> str:
        return (
            f"DrawdownMonitor("
            f"peak=${self._peak_equity:,.2f}, "
            f"current=${self._current_equity:,.2f}, "
            f"dd={self.current_drawdown:.2%}, "
            f"limit={self._limits.max_drawdown_pct:.2%})"
        )
