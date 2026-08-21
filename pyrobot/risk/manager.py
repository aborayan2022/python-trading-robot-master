"""Risk Manager — central orchestration for all risk management.

Integrates:
    - KillSwitch (hard stop)
    - RiskLimits (configuration)
    - PositionSizer (order sizing)
    - ExposureMonitor (portfolio exposure)
    - DrawdownMonitor (drawdown protection)
    - CircuitBreaker (automatic halt)

The RiskManager is the single authority for all risk decisions.
No order should bypass it.

Usage::

    rm = RiskManager(limits=RiskLimits.conservative())

    # Pre-trade check (called by ExecutionEngine)
    approved, reason = rm.check_order(
        order=order,
        positions=current_positions,
        prices=current_prices,
        equity=account_equity,
    )

    # Post-trade update
    rm.record_fill(order, fill_price=150.0, fill_qty=100)

    # Equity update
    rm.update_equity(100_000.0)
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import threading

from pyrobot.exceptions import (
    KillSwitchError,
    PositionLimitError,
    DailyLossLimitError,
    DrawdownLimitError,
    ExposureLimitError,
    RiskError,
)
from pyrobot.logging_config import get_logger
from pyrobot.models.order import Order, OrderSide
from pyrobot.risk.limits import RiskLimits
from pyrobot.risk.kill_switch import KillSwitch, KillSwitchReason
from pyrobot.risk.position_sizer import PositionSizer
from pyrobot.risk.exposure import ExposureMonitor, ExposureSnapshot
from pyrobot.risk.drawdown import DrawdownMonitor
from pyrobot.risk.circuit_breaker import CircuitBreaker
from pyrobot.risk.decision import RiskDecision

logger = get_logger("risk_manager")


class RiskManager:
    """Central risk management authority for the trading platform.

    Args:
        limits: RiskLimits configuration. Defaults to standard limits.
        kill_switch: Optional shared KillSwitch instance.
        sector_map: Optional symbol → sector mapping for concentration checks.
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        kill_switch: KillSwitch | None = None,
        sector_map: Dict[str, str] | None = None,
    ) -> None:
        self._limits = limits or RiskLimits()
        self._limits.validate()

        self._kill_switch = kill_switch or KillSwitch()
        self._position_sizer = PositionSizer(limits=self._limits)
        self._exposure_monitor = ExposureMonitor(
            limits=self._limits, sector_map=sector_map
        )
        self._drawdown_monitor = DrawdownMonitor(limits=self._limits)
        self._circuit_breaker = CircuitBreaker(limits=self._limits)

        # Order throttle tracking
        self._last_order_times: Dict[str, datetime] = {}
        self._last_kill_switch_reset: Optional[datetime] = None

        # Daily PnL tracking
        self._daily_realized_pnl: float = 0.0
        self._daily_date: Optional[str] = None
        self._positions: Dict[str, Dict[str, float]] = {}

        self._lock = threading.RLock()

    # ── Pre-trade checks ──────────────────────────────────────────────────────

    def evaluate_order(
        self,
        order: Order,
        positions: Dict[str, float],
        prices: Dict[str, float],
        equity: float,
    ) -> RiskDecision:
        """Run all pre-trade risk checks and return a comprehensive RiskDecision.

        Args:
            order: The Order to validate.
            positions: Current positions (symbol → quantity).
            prices: Current prices (symbol → price).
            equity: Total portfolio equity.

        Returns:
            RiskDecision instance with checks passed/failed and metrics snapshot.

        Raises:
            KillSwitchError: If kill switch is active or drawdown breached (hard stop).
        """
        with self._lock:
            checks_passed: List[str] = []
            checks_failed: List[str] = []

            # Current metrics snapshot
            metrics = {
                "equity": equity,
                "current_drawdown": self._drawdown_monitor.current_drawdown,
                "daily_loss_pct": self._drawdown_monitor.daily_loss_pct,
                "daily_realized_pnl": self._daily_realized_pnl,
                "circuit_breaker_scale": self._circuit_breaker.position_scale,
            }

            # 1. Kill switch guard (hard stop — always checked first)
            self._kill_switch.guard()
            checks_passed.append("kill_switch_guard")

            # 2. Circuit breaker check
            if self._circuit_breaker.is_open:
                checks_failed.append("circuit_breaker")
                return RiskDecision(
                    approved=False,
                    reason=f"Circuit breaker OPEN: {self._circuit_breaker.status}",
                    order_id=order.client_order_id,
                    symbol=order.symbol,
                    checks_passed=checks_passed,
                    checks_failed=checks_failed,
                    metrics=metrics,
                )
            checks_passed.append("circuit_breaker")

            # 3. Cooldown after kill switch reset
            if not self._check_cooldown():
                checks_failed.append("kill_switch_cooldown")
                return RiskDecision(
                    approved=False,
                    reason=(
                        "Cooldown active after kill switch reset. "
                        f"Wait {self._limits.cooldown_after_kill_switch_seconds}s"
                    ),
                    order_id=order.client_order_id,
                    symbol=order.symbol,
                    checks_passed=checks_passed,
                    checks_failed=checks_failed,
                    metrics=metrics,
                )
            checks_passed.append("kill_switch_cooldown")

            # 4. Order throttle
            if not self._check_order_throttle(order.symbol):
                checks_failed.append("order_throttle")
                return RiskDecision(
                    approved=False,
                    reason=(
                        f"Order throttle: minimum {self._limits.min_order_interval_seconds}s "
                        f"between orders for {order.symbol}"
                    ),
                    order_id=order.client_order_id,
                    symbol=order.symbol,
                    checks_passed=checks_passed,
                    checks_failed=checks_failed,
                    metrics=metrics,
                )
            checks_passed.append("order_throttle")

            # 5. Drawdown check
            if self._drawdown_monitor.is_breached:
                self._kill_switch.activate(
                    KillSwitchReason.MAX_DRAWDOWN,
                    detail=self._drawdown_monitor.status(),
                )
                raise KillSwitchError(
                    f"Max drawdown breached: {self._drawdown_monitor.status()}"
                )
            checks_passed.append("max_drawdown")

            # 6. Daily loss check
            if self._drawdown_monitor.is_daily_breached:
                self._kill_switch.activate(
                    KillSwitchReason.DAILY_LOSS_LIMIT,
                    detail=f"daily_loss={self._drawdown_monitor.daily_loss_pct:.2%}",
                )
                raise KillSwitchError(
                    f"Daily loss limit breached: "
                    f"{self._drawdown_monitor.daily_loss_pct:.2%}"
                )
            checks_passed.append("daily_loss_limit")

            # 7. Exposure check
            side_str = "BUY" if order.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER) else "SELL"
            exposure_ok, exposure_reason = self._exposure_monitor.check_order(
                current_exposure=self._get_exposure(positions, prices, equity),
                symbol=order.symbol,
                side=side_str,
                quantity=order.quantity,
                price=self._get_fill_price(order, prices),
                account_equity=equity,
            )
            if not exposure_ok:
                checks_failed.append("exposure_limits")
                return RiskDecision(
                    approved=False,
                    reason=exposure_reason,
                    order_id=order.client_order_id,
                    symbol=order.symbol,
                    checks_passed=checks_passed,
                    checks_failed=checks_failed,
                    metrics=metrics,
                )
            checks_passed.append("exposure_limits")

            return RiskDecision(
                approved=True,
                reason="OK",
                order_id=order.client_order_id,
                symbol=order.symbol,
                checks_passed=checks_passed,
                checks_failed=checks_failed,
                metrics=metrics,
            )

    def check_order(
        self,
        order: Order,
        positions: Dict[str, float],
        prices: Dict[str, float],
        equity: float,
    ) -> Tuple[bool, str]:
        """Run all pre-trade risk checks on an order.

        Args:
            order: The Order to validate.
            positions: Current positions (symbol → quantity).
            prices: Current prices (symbol → price).
            equity: Total portfolio equity.

        Returns:
            Tuple of (approved: bool, reason: str).
        """
        decision = self.evaluate_order(order, positions, prices, equity)
        return decision.approved, decision.reason

    def calculate_position_size(
        self,
        account_equity: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        price: float,
        confidence: float = 1.0,
        method: str = "kelly",
    ) -> int:
        """Calculate optimal position size.

        Args:
            account_equity: Current portfolio equity.
            win_rate: Historical win rate.
            avg_win: Average winning trade return.
            avg_loss: Average losing trade return.
            price: Current market price.
            confidence: Signal confidence (0.0 to 1.0).
            method: "kelly" or "fixed_fraction".

        Returns:
            Recommended number of shares.
        """
        if method == "kelly":
            qty = self._position_sizer.kelly_size(
                account_equity=account_equity,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                price=price,
                confidence=confidence,
            )
        else:
            stop_distance = price * 0.02  # Default 2% stop
            qty = self._position_sizer.fixed_fraction_size(
                account_equity=account_equity,
                risk_per_trade_pct=self._limits.max_daily_loss_pct / 2,
                stop_distance=stop_distance,
                price=price,
                confidence=confidence,
            )

        # Apply circuit breaker scaling
        qty = int(qty * self._circuit_breaker.position_scale)

        return qty

    # ── Post-trade updates ────────────────────────────────────────────────────

    def record_fill(
        self,
        order: Order,
        fill_price: float,
        fill_qty: float,
        commission: float = 0.0,
    ) -> float:
        """Record a trade fill, update internal position book, and update all risk trackers.

        Args:
            order: The filled Order.
            fill_price: Actual fill price.
            fill_qty: Quantity filled.
            commission: Optional commission/fees for the fill.

        Returns:
            Realized PnL from this fill.
        """
        with self._lock:
            pnl = self._estimate_and_update_pnl(order, fill_price, fill_qty, commission)
            self._daily_realized_pnl += pnl
            self._circuit_breaker.record_trade_result(pnl)

            logger.info(
                "Trade recorded: symbol=%s side=%s qty=%.0f price=%.2f pnl=%.2f comm=%.2f",
                order.symbol, order.side.value, fill_qty, fill_price, pnl, commission,
            )
            return pnl

    def sync_position(self, symbol: str, quantity: float, avg_price: float) -> None:
        """Explicitly update or synchronize position state in risk tracking."""
        with self._lock:
            self._positions[symbol] = {"qty": float(quantity), "avg_price": float(avg_price)}

    def get_tracked_positions(self) -> Dict[str, Dict[str, float]]:
        """Get copy of currently tracked positions in risk manager."""
        with self._lock:
            return {s: dict(p) for s, p in self._positions.items()}

    def update_equity(self, equity: float) -> None:
        """Update equity and check drawdown/daily loss limits.

        Args:
            equity: Current total portfolio equity.
        """
        with self._lock:
            self._drawdown_monitor.update(equity)

            # Check drawdown
            if self._drawdown_monitor.is_breached:
                self._kill_switch.activate(
                    KillSwitchReason.MAX_DRAWDOWN,
                    detail=self._drawdown_monitor.status(),
                )
                logger.critical(
                    "Drawdown limit breached — kill switch activated: %s",
                    self._drawdown_monitor.status(),
                )

            # Check daily loss
            if self._drawdown_monitor.is_daily_breached:
                self._kill_switch.activate(
                    KillSwitchReason.DAILY_LOSS_LIMIT,
                    detail=f"daily_loss={self._drawdown_monitor.daily_loss_pct:.2%}",
                )
                logger.critical(
                    "Daily loss limit breached — kill switch activated"
                )

            # Feed drawdown to circuit breaker
            self._circuit_breaker.check_drawdown_breach(
                self._drawdown_monitor.current_drawdown
            )

    def set_daily_start(self, equity: float, date_str: str) -> None:
        """Record start-of-day equity for daily loss tracking."""
        with self._lock:
            self._drawdown_monitor.set_daily_start(equity, date_str)
            self._daily_realized_pnl = 0.0
            self._daily_date = date_str

    # ── Kill switch integration ───────────────────────────────────────────────

    def activate_kill_switch(
        self,
        reason: KillSwitchReason,
        detail: str = "",
    ) -> None:
        """Manually activate the kill switch."""
        self._kill_switch.activate(reason, detail=detail)

    def reset_kill_switch(self, confirmed: bool = False) -> None:
        """Reset the kill switch and record cooldown start."""
        self._kill_switch.reset(confirmed=confirmed)
        with self._lock:
            self._last_kill_switch_reset = datetime.now(timezone.utc)
            self._circuit_breaker.force_close()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch

    @property
    def drawdown_monitor(self) -> DrawdownMonitor:
        return self._drawdown_monitor

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def exposure_monitor(self) -> ExposureMonitor:
        return self._exposure_monitor

    @property
    def position_sizer(self) -> PositionSizer:
        return self._position_sizer

    @property
    def limits(self) -> RiskLimits:
        return self._limits

    @property
    def daily_realized_pnl(self) -> float:
        return self._daily_realized_pnl

    def status(self) -> Dict:
        """Full risk status snapshot."""
        return {
            "kill_switch_active": self._kill_switch.is_active,
            "circuit_breaker_state": self._circuit_breaker.state.value,
            "circuit_breaker_status": self._circuit_breaker.status,
            "drawdown": self._drawdown_monitor.current_drawdown,
            "max_drawdown": self._drawdown_monitor.max_drawdown,
            "daily_loss_pct": self._drawdown_monitor.daily_loss_pct,
            "daily_realized_pnl": self._daily_realized_pnl,
            "position_scale": self._circuit_breaker.position_scale,
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_exposure(
        self,
        positions: Dict[str, float],
        prices: Dict[str, float],
        equity: float,
    ) -> ExposureSnapshot:
        """Calculate current exposure snapshot."""
        return self._exposure_monitor.calculate_exposure(
            positions=positions,
            prices=prices,
            account_equity=equity,
        )

    def _get_fill_price(self, order: Order, prices: Dict[str, float]) -> float:
        """Estimate fill price for risk checks."""
        if order.limit_price:
            return order.limit_price
        return prices.get(order.symbol, 0.0)

    def _check_cooldown(self) -> bool:
        """Check if cooldown after kill switch reset has elapsed."""
        if self._last_kill_switch_reset is None:
            return True
        elapsed = (
            datetime.now(timezone.utc) - self._last_kill_switch_reset
        ).total_seconds()
        return elapsed >= self._limits.cooldown_after_kill_switch_seconds

    def _check_order_throttle(self, symbol: str) -> bool:
        """Check minimum interval between orders for the same symbol."""
        last_time = self._last_order_times.get(symbol)
        if last_time is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
        if elapsed < self._limits.min_order_interval_seconds:
            return False
        self._last_order_times[symbol] = datetime.now(timezone.utc)
        return True

    def _estimate_and_update_pnl(
        self,
        order: Order,
        fill_price: float,
        fill_qty: float,
        commission: float = 0.0,
    ) -> float:
        """Estimate realized PnL from a fill and update the internal position book."""
        pos = self._positions.get(order.symbol, {"qty": 0.0, "avg_price": 0.0})
        curr_qty = pos["qty"]
        curr_avg_price = pos["avg_price"]
        realized_pnl = -commission

        is_buy = order.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER)
        is_sell = order.side in (OrderSide.SELL, OrderSide.SELL_SHORT)

        if is_buy:
            if curr_qty < 0:  # Covering short position
                closed_qty = min(fill_qty, abs(curr_qty))
                # Short profit: entry_price - exit_price
                realized_pnl += closed_qty * (curr_avg_price - fill_price)
                rem_qty = curr_qty + fill_qty
                if rem_qty > 0:  # flipped to long
                    self._positions[order.symbol] = {"qty": rem_qty, "avg_price": fill_price}
                elif rem_qty == 0:
                    self._positions[order.symbol] = {"qty": 0.0, "avg_price": 0.0}
                else:
                    self._positions[order.symbol] = {"qty": rem_qty, "avg_price": curr_avg_price}
            else:  # Adding to long position
                new_qty = curr_qty + fill_qty
                if new_qty > 0:
                    new_avg = ((curr_qty * curr_avg_price) + (fill_qty * fill_price)) / new_qty
                    self._positions[order.symbol] = {"qty": new_qty, "avg_price": new_avg}
                else:
                    self._positions[order.symbol] = {"qty": 0.0, "avg_price": 0.0}

        elif is_sell:
            if curr_qty > 0:  # Closing long position
                closed_qty = min(fill_qty, curr_qty)
                # Long profit: exit_price - entry_price
                realized_pnl += closed_qty * (fill_price - curr_avg_price)
                rem_qty = curr_qty - fill_qty
                if rem_qty < 0:  # flipped to short
                    self._positions[order.symbol] = {"qty": rem_qty, "avg_price": fill_price}
                elif rem_qty == 0:
                    self._positions[order.symbol] = {"qty": 0.0, "avg_price": 0.0}
                else:
                    self._positions[order.symbol] = {"qty": rem_qty, "avg_price": curr_avg_price}
            else:  # Adding to short position
                new_qty = curr_qty - fill_qty
                if abs(new_qty) > 0:
                    new_avg = ((abs(curr_qty) * curr_avg_price) + (fill_qty * fill_price)) / abs(new_qty)
                    self._positions[order.symbol] = {"qty": new_qty, "avg_price": new_avg}
                else:
                    self._positions[order.symbol] = {"qty": 0.0, "avg_price": 0.0}

        return realized_pnl

    def _estimate_pnl(self, order: Order, fill_price: float, fill_qty: float) -> float:
        """Estimate PnL from a fill without updating internal state."""
        pos = self._positions.get(order.symbol, {"qty": 0.0, "avg_price": 0.0})
        curr_qty = pos["qty"]
        curr_avg_price = pos["avg_price"]

        if order.side in (OrderSide.BUY, OrderSide.BUY_TO_COVER) and curr_qty < 0:
            closed_qty = min(fill_qty, abs(curr_qty))
            return closed_qty * (curr_avg_price - fill_price)
        elif order.side in (OrderSide.SELL, OrderSide.SELL_SHORT) and curr_qty > 0:
            closed_qty = min(fill_qty, curr_qty)
            return closed_qty * (fill_price - curr_avg_price)
        return 0.0

    def __repr__(self) -> str:
        return (
            f"RiskManager("
            f"kill_switch={'ACTIVE' if self._kill_switch.is_active else 'inactive'}, "
            f"circuit={self._circuit_breaker.state.value}, "
            f"dd={self._drawdown_monitor.current_drawdown:.2%})"
        )
