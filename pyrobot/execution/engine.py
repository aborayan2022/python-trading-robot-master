"""Execution Engine — the single gateway for all order submissions.

Every order in the platform MUST pass through the ExecutionEngine.
No broker adapter should be called directly from a strategy.

The submission pipeline::

    ExecutionEngine.submit(order)
        │
        ├─ [1] KillSwitch.guard()              ← halt if kill switch active
        ├─ [2] Duplicate detection             ← via OrderManager
        ├─ [3] Order validation                ← symbol, qty, type checks
        ├─ [4] Risk pre-check                  ← (hook for future RiskEngine)
        ├─ [5] Broker.place_order(order)       ← canonical Order object
        ├─ [6] OrderManager.mark_submitted()   ← record broker_order_id
        └─ [7] Return broker response dict

On any transient error the submission is retried (via retry policy).
On permanent errors (rejected, invalid, kill switch) the error propagates.

Usage::

    engine = ExecutionEngine(
        broker=alpaca_broker,
        order_manager=order_manager,
        kill_switch=kill_switch,
        account_id="ACC123",
    )

    order = order_manager.create_from_signal(signal, quantity=10)
    response = engine.submit(order)
"""

from typing import Dict, Optional

from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import (
    NON_RETRYABLE_EXCEPTIONS,
    ExecutionError,
    KillSwitchError,
)
from pyrobot.execution.order_manager import OrderManager
from pyrobot.execution.reconciliation import _BROKER_STATUS_MAP
from pyrobot.logging_config import get_logger
from pyrobot.models.order import Order, OrderState, OrderType
from pyrobot.risk.decision import RiskDecision
from pyrobot.risk.kill_switch import KillSwitch
from pyrobot.risk.manager import RiskManager
from pyrobot.utils.retry import is_retryable_order_error

logger = get_logger("execution_engine")


class ExecutionEngine:
    """Single gateway for all order submissions.

    Args:
        broker: The active :class:`BrokerInterface` implementation.
        order_manager: Platform :class:`OrderManager` instance.
        kill_switch: Platform :class:`KillSwitch` instance.
        account_id: Broker account identifier.
        max_retries: Maximum retry attempts for transient broker errors.
        dry_run: If True, log orders but do NOT submit to the broker.
            Useful for shadow mode testing.
        risk_manager: Platform :class:`RiskManager` instance. If None,
            a default instance will be created with the provided kill_switch.
        audit_ledger: Platform :class:`AuditLedger` instance for tamper-evident logging.
    """

    def __init__(
        self,
        broker: BrokerInterface,
        order_manager: OrderManager,
        kill_switch: KillSwitch,
        account_id: str = "",
        max_retries: int = 3,
        dry_run: bool = False,
        risk_manager: RiskManager | None = None,
        audit_ledger: AuditLedger | None = None,
    ) -> None:
        self._broker = broker
        self._order_manager = order_manager
        self._kill_switch = kill_switch
        self._account_id = account_id
        self._max_retries = max_retries
        self._dry_run = dry_run
        self._risk_manager = (
            risk_manager if risk_manager is not None else RiskManager(kill_switch=kill_switch)
        )
        self._audit_ledger = audit_ledger if audit_ledger is not None else AuditLedger()

        self._submission_count: int = 0
        self._failure_count: int = 0
        self._consecutive_failures: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def set_risk_context(
        self,
        positions: Dict[str, float],
        prices: Dict[str, float],
        equity: float,
    ) -> None:
        """Set the current risk context for pre-trade checks.

        Args:
            positions: Current positions (symbol → quantity).
            prices: Current prices (symbol → price).
            equity: Total portfolio equity.
        """
        self._risk_positions = positions
        self._risk_prices = prices
        self._risk_equity = equity

    def submit(self, order: Order) -> Dict:
        """Submit an order through the full execution pipeline.

        Args:
            order: A :class:`Order` instance previously registered with
                :class:`OrderManager`.

        Returns:
            Broker response dict with at minimum::

                {
                    "order_id": str,       # broker-assigned ID
                    "status": str,         # broker status string
                    "request_body": dict,  # what was sent
                }

        Raises:
            KillSwitchError: If the kill switch is active.
            DuplicateOrderError: If the order was already submitted.
            OrderRejectedError: If the broker rejects the order (non-retryable).
            ExecutionError: For other execution failures.
        """
        # ── Step 1: Kill switch guard ─────────────────────────────────────
        try:
            self._kill_switch.guard()
        except KillSwitchError as exc:
            self._audit_ledger.record(
                action=AuditAction.KILL_SWITCH_TRIGGERED,
                symbol=order.symbol,
                order_id=order.client_order_id,
                strategy_id=order.strategy_id,
                details={
                    "reason": exc.reason,
                    "stage": "pre_submit_guard",
                    "blocked": True,
                },
            )
            logger.critical(
                "Kill switch blocked order submission: coid=%s reason=%s",
                order.client_order_id,
                exc.reason,
            )
            raise

        # ── Step 2: Validate order state ──────────────────────────────────
        if order.status != OrderState.NEW:
            raise ExecutionError(
                f"Cannot submit order {order.client_order_id!r}: "
                f"expected state NEW, got {order.status.value}. "
                "This may indicate a duplicate submission attempt."
            )

        # ── Step 3: Basic order validation ────────────────────────────────
        self._validate(order)

        # ── Step 4: Risk pre-check hook (mandatory RiskEngine gate) ──────
        risk_decision = self._pre_trade_risk_check(order)
        self._audit_ledger.record(
            action=AuditAction.RISK_EVALUATED,
            symbol=order.symbol,
            order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            details=risk_decision.to_dict(),
        )

        # ── Step 5: Submit to broker (with retry) ─────────────────────────
        logger.info(
            "Submitting order: coid=%s symbol=%s side=%s qty=%s type=%s dry_run=%s",
            order.client_order_id,
            order.symbol,
            order.side.value,
            order.quantity,
            order.order_type.value,
            self._dry_run,
        )

        if self._dry_run:
            res = self._dry_run_response(order)
            self._audit_ledger.record(
                action=AuditAction.ORDER_SUBMITTED,
                symbol=order.symbol,
                order_id=order.client_order_id,
                strategy_id=order.strategy_id,
                details={"dry_run": True, "response": res},
            )
            return res

        try:
            response = self._submit_with_retry(order)
        except NON_RETRYABLE_EXCEPTIONS as exc:
            self._failure_count += 1
            self._consecutive_failures += 1
            self._order_manager.mark_rejected(
                order.client_order_id,
                reason=str(exc),
            )
            self._audit_ledger.record(
                action=AuditAction.ORDER_REJECTED,
                symbol=order.symbol,
                order_id=order.client_order_id,
                strategy_id=order.strategy_id,
                details={"error": str(exc), "permanent": True},
            )
            logger.error(
                "Order permanently rejected: coid=%s error=%s",
                order.client_order_id,
                exc,
            )
            raise

        except Exception as exc:
            self._failure_count += 1
            self._consecutive_failures += 1
            # Transient errors that exhausted all retries → UNKNOWN
            self._order_manager.mark_unknown(
                order.client_order_id,
                reason=f"Exhausted retries: {exc}",
            )
            self._audit_ledger.record(
                action=AuditAction.ORDER_REJECTED,
                symbol=order.symbol,
                order_id=order.client_order_id,
                strategy_id=order.strategy_id,
                details={"error": str(exc), "state": "UNKNOWN"},
            )
            logger.error(
                "Order state set to UNKNOWN after retry exhaustion: coid=%s error=%s",
                order.client_order_id,
                exc,
            )
            raise ExecutionError(
                f"Order submission failed after {self._max_retries} retries: {exc}"
            ) from exc

        # ── Step 6: Record broker_order_id ────────────────────────────────
        broker_order_id = response.get("order_id", "")
        if not broker_order_id:
            logger.warning(
                "Broker response missing order_id for coid=%s. "
                "Order will remain in SUBMITTED state.",
                order.client_order_id,
            )

        self._order_manager.mark_submitted(
            order.client_order_id,
            broker_order_id=broker_order_id,
        )

        self._submission_count += 1
        self._consecutive_failures = 0  # Reset on success

        self._audit_ledger.record(
            action=AuditAction.ORDER_SUBMITTED,
            symbol=order.symbol,
            order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            details={
                "broker_order_id": broker_order_id,
                "status": response.get("status"),
                "quantity": order.quantity,
                "side": order.side.value,
            },
        )

        logger.info(
            "Order submitted successfully: coid=%s broker_id=%s status=%s",
            order.client_order_id,
            broker_order_id,
            response.get("status"),
        )

        return response

    def cancel_order(self, client_order_id: str) -> bool:
        """Request cancellation of a working order at the broker.

        Pipeline::

            1. Validate the order exists and is in a cancellable state
            2. OrderManager.mark_cancel_pending()   ← CANCEL_PENDING
            3. Broker.cancel_order(broker_order_id)
            4. On success: mark CANCELLED + audit ORDER_CANCELLED
               On failure: remain CANCEL_PENDING and raise ExecutionError

        Args:
            client_order_id: Our internal idempotency key.

        Returns:
            True if the broker confirmed the cancellation.

        Raises:
            ExecutionError: If the order is unknown, not yet submitted,
                already terminal, has no broker_order_id, or the broker
                fails/refuses the cancellation (order stays CANCEL_PENDING).
        """
        order = self._order_manager.get(client_order_id)
        if order is None:
            raise ExecutionError(
                f"Cannot cancel order {client_order_id!r}: unknown client_order_id."
            )

        if order.status is OrderState.NEW:
            raise ExecutionError(
                f"Cannot cancel order {client_order_id!r}: order has not been "
                "submitted to a broker yet."
            )

        if order.status not in (
            OrderState.SUBMITTED,
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.CANCEL_PENDING,
        ):
            raise ExecutionError(
                f"Cannot cancel order {client_order_id!r}: order is in "
                f"terminal state {order.status.value}."
            )

        if not order.broker_order_id:
            raise ExecutionError(
                f"Cannot cancel order {client_order_id!r}: no broker_order_id "
                "assigned — order may not have reached the broker."
            )

        # Idempotent retry: an order already in CANCEL_PENDING skips the
        # transition (CANCEL_PENDING → CANCEL_PENDING is not a valid edge).
        if order.status is not OrderState.CANCEL_PENDING:
            self._order_manager.mark_cancel_pending(client_order_id)

        logger.info(
            "Cancelling order: coid=%s broker_id=%s",
            client_order_id,
            order.broker_order_id,
        )

        try:
            cancelled = self._broker.cancel_order(order.broker_order_id)
        except Exception as exc:
            self._failure_count += 1
            self._consecutive_failures += 1
            logger.error(
                "Broker error while cancelling order: coid=%s error=%s — "
                "order left in CANCEL_PENDING.",
                client_order_id,
                exc,
            )
            raise ExecutionError(
                f"Broker error while cancelling order {client_order_id!r}: {exc}"
            ) from exc

        if not cancelled:
            self._failure_count += 1
            self._consecutive_failures += 1
            logger.error(
                "Broker refused cancellation of order %r — order left in "
                "CANCEL_PENDING.",
                client_order_id,
            )
            raise ExecutionError(
                f"Broker refused to cancel order {client_order_id!r} "
                f"(broker_order_id={order.broker_order_id!r}) — order left "
                "in CANCEL_PENDING."
            )

        self._order_manager.mark_cancelled(client_order_id)

        self._audit_ledger.record(
            action=AuditAction.ORDER_CANCELLED,
            symbol=order.symbol,
            order_id=client_order_id,
            strategy_id=order.strategy_id,
            details={
                "broker_order_id": order.broker_order_id,
                "status": "CANCELLED",
            },
        )

        logger.info(
            "Order cancelled: coid=%s broker_id=%s",
            client_order_id,
            order.broker_order_id,
        )
        return True

    def poll_status(self, client_order_id: str) -> Dict:
        """Poll the broker for the latest status of an order and apply it.

        This is the fill-confirmation path: when the broker reports the
        order as (partially) filled, the OrderManager state is updated and
        an ORDER_FILLED audit event is recorded.

        Args:
            client_order_id: Our internal idempotency key.

        Returns:
            The raw broker status dict
            (``{'order_id', 'status', 'filled_quantity', 'avg_fill_price', ...}``).

        Raises:
            ExecutionError: If the order is unknown or has no
                broker_order_id yet.
        """
        order = self._order_manager.get(client_order_id)
        if order is None:
            raise ExecutionError(
                f"Cannot poll order {client_order_id!r}: unknown client_order_id."
            )

        if not order.broker_order_id:
            raise ExecutionError(
                f"Cannot poll order {client_order_id!r}: no broker_order_id "
                "assigned — order may not have reached the broker."
            )

        broker_status = self._broker.get_order_status(
            account=self._account_id,
            order_id=order.broker_order_id,
        )

        status_str = str(broker_status.get("status", "UNKNOWN")).lower()
        state = _BROKER_STATUS_MAP.get(status_str, OrderState.UNKNOWN)
        filled_qty = float(broker_status.get("filled_quantity", 0) or 0)
        avg_price = float(broker_status.get("avg_fill_price", 0) or 0)

        # Apply state updates only on change (idempotent re-polls must not
        # raise OrderStateError on self-transitions).
        if state is OrderState.FILLED and order.status is not OrderState.FILLED:
            self._order_manager.mark_filled(client_order_id, filled_qty, avg_price)
            self._record_fill(order, filled_qty, avg_price, partial=False)
        elif (
            state is OrderState.PARTIALLY_FILLED
            and order.status is not OrderState.PARTIALLY_FILLED
        ):
            self._order_manager.mark_partially_filled(
                client_order_id, filled_qty, avg_price
            )
            self._record_fill(order, filled_qty, avg_price, partial=True)
        elif state is OrderState.CANCELLED and order.status is not OrderState.CANCELLED:
            self._order_manager.mark_cancelled(client_order_id)
        elif state is OrderState.REJECTED and order.status is not OrderState.REJECTED:
            self._order_manager.mark_rejected(client_order_id, reason="broker")
        elif (
            state is OrderState.ACKNOWLEDGED
            and order.status is OrderState.SUBMITTED
        ):
            self._order_manager.mark_acknowledged(client_order_id)
        else:
            logger.debug(
                "Poll left order unchanged: coid=%s state=%s broker_status=%r",
                client_order_id,
                order.status.value,
                status_str,
            )

        return broker_status

    def _record_fill(
        self,
        order: Order,
        filled_qty: float,
        avg_price: float,
        partial: bool = False,
    ) -> None:
        """Record an ORDER_FILLED audit event for a confirmed fill."""
        self._audit_ledger.record(
            action=AuditAction.ORDER_FILLED,
            symbol=order.symbol,
            order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            details={
                "broker_order_id": order.broker_order_id,
                "filled_quantity": filled_qty,
                "avg_fill_price": avg_price,
                "partial": partial,
                "source": "poll_status",
            },
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _validate(self, order: Order) -> None:
        """Basic order field validation before broker submission.

        Raises:
            ValueError: On invalid order fields.
        """
        if not order.symbol or not order.symbol.strip():
            raise ValueError(
                f"Order {order.client_order_id!r} has an empty symbol."
            )

        if order.quantity <= 0:
            raise ValueError(
                f"Order {order.client_order_id!r} has invalid quantity "
                f"{order.quantity} — must be positive."
            )

        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if order.limit_price is None or order.limit_price <= 0:
                raise ValueError(
                    f"Order {order.client_order_id!r} is type {order.order_type.value} "
                    "but has no valid limit_price."
                )

        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if order.stop_price is None or order.stop_price <= 0:
                raise ValueError(
                    f"Order {order.client_order_id!r} is type {order.order_type.value} "
                    "but has no valid stop_price."
                )

    def _pre_trade_risk_check(self, order: Order) -> RiskDecision:
        """Run pre-trade risk validation via the RiskManager.

        Fails closed: if the risk context cannot value the order (no price
        for the order's symbol), the order is REJECTED rather than valued
        at qty * 0.0 and allowed to pass the exposure checks.

        Returns:
            RiskDecision: The evaluation result.

        Raises:
            ExecutionError: If the risk context cannot value the order or
                the risk manager rejects the order.
            KillSwitchError: If drawdown or daily loss limits are breached.
        """
        prices = getattr(self, "_risk_prices", {})

        # Fail-closed guard: an unpriceable order must never reach the
        # exposure checks (order_value would silently compute as qty * 0.0).
        price = order.limit_price if order.limit_price else prices.get(order.symbol)
        if price is None or price <= 0:
            reason = (
                f"Risk context has no price for symbol {order.symbol!r} — "
                "cannot value order (fail-closed)."
            )
            self._order_manager.mark_rejected(order.client_order_id, reason=reason)
            self._audit_ledger.record(
                action=AuditAction.ORDER_REJECTED,
                symbol=order.symbol,
                order_id=order.client_order_id,
                strategy_id=order.strategy_id,
                details={"reason": reason, "risk_rejection": True, "fail_closed": True},
            )
            logger.error(
                "Order rejected (fail-closed): coid=%s symbol=%s — no price in "
                "risk context.",
                order.client_order_id,
                order.symbol,
            )
            raise ExecutionError(
                f"Order {order.client_order_id!r} rejected: {reason}"
            )

        decision = self._risk_manager.evaluate_order(
            order=order,
            positions=getattr(self, "_risk_positions", {}),
            prices=prices,
            equity=getattr(self, "_risk_equity", 0.0),
        )
        if not decision.approved:
            self._audit_ledger.record(
                action=AuditAction.ORDER_REJECTED,
                symbol=order.symbol,
                order_id=order.client_order_id,
                strategy_id=order.strategy_id,
                details={"reason": decision.reason, "risk_rejection": True},
            )
            raise ExecutionError(
                f"Risk manager rejected order {order.client_order_id!r}: {decision.reason}"
            )
        return decision

    def _submit_with_retry(self, order: Order) -> Dict:
        """Submit the order to the broker, retrying on transient errors.

        Uses the :func:`retry` decorator pattern inline for configurable
        max_retries.
        """
        order_dict = order.to_legacy_dict()
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                return self._broker.place_order(
                    account=self._account_id,
                    order=order_dict,
                )
            except Exception as exc:
                last_exc = exc

                # Non-retryable → propagate immediately
                if isinstance(exc, NON_RETRYABLE_EXCEPTIONS):
                    raise

                if not is_retryable_order_error(exc):
                    raise

                if attempt >= self._max_retries:
                    break

                import time
                delay = min(1.0 * (2 ** attempt), 30.0)
                logger.warning(
                    "Transient broker error (attempt %d/%d) for coid=%s: %s — "
                    "retrying in %.1fs",
                    attempt + 1,
                    self._max_retries + 1,
                    order.client_order_id,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise last_exc  # type: ignore[misc]

    def _dry_run_response(self, order: Order) -> Dict:
        """Return a synthetic broker response for dry-run / shadow mode."""
        logger.info(
            "[DRY RUN] Order NOT submitted to broker: coid=%s symbol=%s side=%s qty=%s",
            order.client_order_id,
            order.symbol,
            order.side.value,
            order.quantity,
        )
        fake_broker_id = f"DRY_{order.client_order_id[:8]}"
        self._order_manager.mark_submitted(order.client_order_id, fake_broker_id)
        return {
            "order_id": fake_broker_id,
            "status": "DRY_RUN",
            "request_body": order.to_legacy_dict(),
        }

    @property
    def audit_ledger(self) -> AuditLedger:
        """Return the audit ledger."""
        return self._audit_ledger

    @property
    def risk_manager(self) -> RiskManager:
        """Return the risk manager."""
        return self._risk_manager

    @property
    def stats(self) -> Dict:
        """Return basic submission statistics."""
        result: Dict = {
            "submission_count": self._submission_count,
            "failure_count": self._failure_count,
            "consecutive_failures": self._consecutive_failures,
            "kill_switch_active": self._kill_switch.is_active,
            "dry_run": self._dry_run,
            "audit_events_count": self._audit_ledger.total_events,
        }
        if self._risk_manager is not None:
            result["risk_manager"] = self._risk_manager.status()
        return result
