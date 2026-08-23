"""Circuit Breaker — automatic trading halt after consecutive failures.

Unlike the KillSwitch (which is operator-managed), the CircuitBreaker
automatically activates when loss streaks or drawdown thresholds are hit,
and automatically deactivates after a cooldown period.

Usage::

    cb = CircuitBreaker(limits=RiskLimits())

    # After each trade result:
    cb.record_trade_result(pnl=-50.0)
    cb.record_trade_result(pnl=-120.0)
    cb.record_trade_result(pnl=-80.0)

    if cb.is_open:
        print(f"Circuit open: {cb.status}")
        # Wait for cooldown...
"""


from datetime import datetime, timezone
from enum import Enum

from pyrobot.logging_config import get_logger
from pyrobot.risk.limits import RiskLimits

logger = get_logger("circuit_breaker")


class CircuitState(str, Enum):
    """Current state of the circuit breaker."""

    CLOSED = "CLOSED"          # Normal operation
    OPEN = "OPEN"              # Trading halted
    HALF_OPEN = "HALF_OPEN"    # Cooldown expired, testing with reduced size


class CircuitBreaker:
    """Automatic trading halt after consecutive failures.

    Args:
        limits: RiskLimits configuration.
        cooldown_seconds: Seconds to wait in OPEN state before transitioning
            to HALF_OPEN. Defaults to 300.
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        cooldown_seconds: int = 300,
    ) -> None:
        self._limits = limits or RiskLimits()
        self._cooldown_seconds = cooldown_seconds

        self._state: CircuitState = CircuitState.CLOSED
        self._consecutive_losses: int = 0
        self._total_trades: int = 0
        self._total_wins: int = 0
        self._total_losses: int = 0
        self._last_trade_pnl: float = 0.0
        self._opened_at: datetime | None = None
        self._half_open_tested: bool = False

    @property
    def state(self) -> CircuitState:
        """Current circuit breaker state."""
        if self._state == CircuitState.OPEN:
            if self._cooldown_expired():
                self._state = CircuitState.HALF_OPEN
                self._half_open_tested = False
                logger.info("Circuit breaker transitioning to HALF_OPEN")
        return self._state

    @property
    def is_open(self) -> bool:
        """True if trading is halted.

        This covers both the OPEN state and a HALF_OPEN state whose single
        test order (see claim_test_order) is already in flight and awaiting
        a trade result.
        """
        state = self.state
        return state == CircuitState.OPEN or (
            state == CircuitState.HALF_OPEN and self._half_open_tested
        )

    @property
    def is_half_open(self) -> bool:
        """True if the circuit is HALF_OPEN (testing recovery)."""
        return self.state == CircuitState.HALF_OPEN

    @property
    def is_closed(self) -> bool:
        """True if the circuit is CLOSED (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def status(self) -> str:
        """Human-readable status string."""
        return (
            f"CircuitState={self._state.value} "
            f"loss_streak={self._consecutive_losses} "
            f"(limit={self._limits.circuit_breaker_loss_streak}) "
            f"trades={self._total_trades} "
            f"W/L={self._total_wins}/{self._total_losses}"
        )

    @property
    def position_scale(self) -> float:
        """Position size multiplier for HALF_OPEN state.

        Returns 1.0 when CLOSED, 0.5 when HALF_OPEN, 0.0 when OPEN.
        """
        state = self.state
        if state == CircuitState.CLOSED:
            return 1.0
        elif state == CircuitState.HALF_OPEN:
            return 0.5
        return 0.0

    def claim_test_order(self) -> bool:
        """Claim the single test-order slot in HALF_OPEN state.

        In HALF_OPEN the breaker allows exactly one test order (sized at
        position_scale 0.5). The slot is held until the next trade result
        is recorded via record_trade_result: a win closes the breaker and
        a loss re-opens it for another cooldown period.

        Returns:
            True if an order may proceed (breaker CLOSED, or the HALF_OPEN
            test slot was successfully claimed); False if the breaker is
            OPEN or the HALF_OPEN test order is already in flight.
        """
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN and not self._half_open_tested:
            self._half_open_tested = True
            logger.info("Circuit breaker HALF_OPEN test order claimed (scale=0.5)")
            return True
        return False

    def record_trade_result(self, pnl: float) -> None:
        """Record the PnL result of a completed trade.

        Args:
            pnl: Profit/loss in dollars (positive = profit).
        """
        self._total_trades += 1
        self._last_trade_pnl = pnl

        if pnl >= 0:
            self._total_wins += 1
            self._consecutive_losses = 0

            if self._state == CircuitState.HALF_OPEN:
                # Recovery confirmed — release the test slot
                self._state = CircuitState.CLOSED
                self._opened_at = None
                self._half_open_tested = False
                logger.info(
                    "Circuit breaker CLOSED — recovery confirmed after %d trades",
                    self._total_trades,
                )
        else:
            self._total_losses += 1
            self._consecutive_losses += 1

            if self._state == CircuitState.HALF_OPEN:
                # Test order failed — re-open for another cooldown period
                self._open("half_open_test_failed")
            elif self._consecutive_losses >= self._limits.circuit_breaker_loss_streak:
                self._open("consecutive_loss_streak")

    def check_drawdown_breach(self, drawdown_pct: float) -> None:
        """Check if drawdown triggers the circuit breaker.

        Args:
            drawdown_pct: Current drawdown as a fraction (e.g. 0.05 for 5%).
        """
        if drawdown_pct >= self._limits.circuit_breaker_drawdown_pct:
            self._open(f"drawdown={drawdown_pct:.2%}")

    def force_open(self, reason: str = "operator") -> None:
        """Manually open the circuit breaker."""
        self._open(reason)

    def force_close(self) -> None:
        """Manually close the circuit breaker (operator override)."""
        self._state = CircuitState.CLOSED
        self._consecutive_losses = 0
        self._opened_at = None
        self._half_open_tested = False
        logger.warning("Circuit breaker FORCE CLOSED by operator")

    def reset(self) -> None:
        """Full reset of all circuit breaker state."""
        self._state = CircuitState.CLOSED
        self._consecutive_losses = 0
        self._total_trades = 0
        self._total_wins = 0
        self._total_losses = 0
        self._last_trade_pnl = 0.0
        self._opened_at = None
        self._half_open_tested = False
        logger.warning("Circuit breaker fully reset")

    def _open(self, reason: str) -> None:
        """Transition to OPEN state."""
        if self._state == CircuitState.OPEN:
            return  # Already open

        self._state = CircuitState.OPEN
        self._opened_at = datetime.now(timezone.utc)
        logger.critical(
            "CIRCUIT BREAKER OPENED — reason=%s loss_streak=%d",
            reason, self._consecutive_losses,
        )

    def _cooldown_expired(self) -> bool:
        """Check if the cooldown period has elapsed."""
        if self._opened_at is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._opened_at).total_seconds()
        return elapsed >= self._cooldown_seconds

    @property
    def win_rate(self) -> float:
        """Historical win rate."""
        if self._total_trades == 0:
            return 0.0
        return self._total_wins / self._total_trades

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self._state.value}, "
            f"loss_streak={self._consecutive_losses}, "
            f"win_rate={self.win_rate:.1%})"
        )
