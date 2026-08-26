"""Order Reconciliation — resolves orders in UNKNOWN state.

When a broker response is ambiguous or a network error occurs during order
submission, the OrderManager sets the order to UNKNOWN.  The reconciler
periodically queries the broker for the true status and updates the order.

Usage::

    reconciler = OrderReconciler(order_manager, broker, account_id="ACC123")

    # Call periodically from a monitoring loop or scheduler:
    reconciler.reconcile_unknown()

    # Or reconcile a single order by its client_order_id:
    reconciler.reconcile_order("coid-xyz-123")
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import BrokerError, ReconciliationError
from pyrobot.execution.order_manager import OrderManager
from pyrobot.logging_config import get_logger
from pyrobot.models.order import Order, OrderState
from pyrobot.risk.kill_switch import KillSwitch, KillSwitchReason

logger = get_logger("reconciler")

# Mapping from broker status strings (lowercase) to canonical OrderState
_BROKER_STATUS_MAP = {
    "new": OrderState.NEW,
    "submitted": OrderState.SUBMITTED,
    "pending_new": OrderState.SUBMITTED,
    "accepted": OrderState.ACKNOWLEDGED,
    "acknowledged": OrderState.ACKNOWLEDGED,
    "partially_filled": OrderState.PARTIALLY_FILLED,
    "partial": OrderState.PARTIALLY_FILLED,
    "filled": OrderState.FILLED,
    "done_for_day": OrderState.FILLED,
    "canceled": OrderState.CANCELLED,
    "cancelled": OrderState.CANCELLED,
    "pending_cancel": OrderState.CANCEL_PENDING,
    "rejected": OrderState.REJECTED,
    "expired": OrderState.EXPIRED,
    "replaced": OrderState.CANCELLED,  # Treat as cancelled for simplicity
}


class OrderReconciler:
    """Reconcile orders in UNKNOWN state against the broker's ground truth.

    Args:
        order_manager: The platform's :class:`OrderManager` instance.
        broker: The active :class:`BrokerInterface` implementation.
        account_id: Broker account identifier.
        max_reconcile_age_secs: Only reconcile orders younger than this many
            seconds.  Set to 0 to disable age filtering.
        audit_ledger: Optional :class:`AuditLedger` — when provided, fills
            confirmed during reconciliation record an ORDER_FILLED event.
    """

    def __init__(
        self,
        order_manager: OrderManager,
        broker: BrokerInterface,
        account_id: str = "",
        max_reconcile_age_secs: float = 86_400,  # 24 hours
        audit_ledger: Optional[AuditLedger] = None,
    ) -> None:
        self._order_manager = order_manager
        self._broker = broker
        self._account_id = account_id
        self._max_age = max_reconcile_age_secs
        self._audit_ledger = audit_ledger

    # ── Public API ────────────────────────────────────────────────────────────

    def reconcile_unknown(self) -> int:
        """Query the broker for all orders currently in UNKNOWN state.

        Returns:
            Number of orders successfully reconciled (state updated).
        """
        unknown_orders: List[Order] = self._order_manager.unknown_orders()

        if not unknown_orders:
            return 0

        logger.info(
            "Reconciliation started: %d UNKNOWN order(s) to resolve.",
            len(unknown_orders),
        )

        resolved = 0
        for order in unknown_orders:
            if self._is_too_old(order):
                logger.warning(
                    "Order %r is older than %ds — skipping reconciliation.",
                    order.client_order_id,
                    self._max_age,
                )
                continue

            try:
                if self.reconcile_order(order.client_order_id):
                    resolved += 1
            except Exception as exc:
                logger.error(
                    "Failed to reconcile order %r: %s",
                    order.client_order_id,
                    exc,
                )

        logger.info("Reconciliation complete: %d/%d resolved.", resolved, len(unknown_orders))
        return resolved

    def reconcile_order(self, client_order_id: str) -> bool:
        """Reconcile a single order against the broker.

        Args:
            client_order_id: The client-side idempotency key.

        Returns:
            True if the order state was updated, False if no change.

        Raises:
            ReconciliationError: If the order has no broker_order_id yet.
        """
        order = self._order_manager.get(client_order_id)
        if order is None:
            raise KeyError(f"Order not found: {client_order_id!r}")

        if not order.broker_order_id:
            raise ReconciliationError(
                f"Cannot reconcile order {client_order_id!r}: "
                "no broker_order_id assigned — order may not have been submitted."
            )

        try:
            broker_status = self._broker.get_order_status(
                account=self._account_id,
                order_id=order.broker_order_id,
            )
        except BrokerError as exc:
            logger.error(
                "Broker error during reconciliation of order %r: %s",
                client_order_id,
                exc,
            )
            return False

        canonical_state = self._map_status(broker_status.get("status", "UNKNOWN"))
        filled_qty = float(broker_status.get("filled_quantity", 0))
        avg_price = float(broker_status.get("avg_fill_price", 0))

        logger.info(
            "Reconciliation result for coid=%r: broker_status=%r → canonical=%s",
            client_order_id,
            broker_status.get("status"),
            canonical_state.value,
        )

        self._apply_reconciled_state(order, canonical_state, filled_qty, avg_price)
        return True

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _map_status(self, broker_status_str: str) -> OrderState:
        """Map a broker status string to a canonical :class:`OrderState`."""
        return _BROKER_STATUS_MAP.get(broker_status_str.lower(), OrderState.UNKNOWN)

    def _apply_reconciled_state(
        self,
        order: Order,
        new_state: OrderState,
        filled_qty: float,
        avg_price: float,
    ) -> None:
        """Apply the reconciled state to the order via OrderManager.

        Resolution MUST go through :meth:`OrderManager.resolve_unknown` so
        the state machine (and its lock) validates the UNKNOWN → X
        transition — the order's status is never mutated directly here.
        """
        coid = order.client_order_id

        if new_state == OrderState.FILLED:
            self._order_manager.resolve_unknown(
                coid, OrderState.FILLED, filled_qty, avg_price
            )
            self._record_fill(order, filled_qty, avg_price, partial=False)
        elif new_state == OrderState.PARTIALLY_FILLED:
            self._order_manager.resolve_unknown(
                coid, OrderState.PARTIALLY_FILLED, filled_qty, avg_price
            )
            self._record_fill(order, filled_qty, avg_price, partial=True)
        elif new_state == OrderState.CANCELLED:
            self._order_manager.resolve_unknown(coid, OrderState.CANCELLED)
        elif new_state == OrderState.REJECTED:
            self._order_manager.resolve_unknown(coid, OrderState.REJECTED)
        elif new_state == OrderState.EXPIRED:
            self._order_manager.resolve_unknown(coid, OrderState.EXPIRED)
        elif new_state == OrderState.SUBMITTED:
            self._order_manager.resolve_unknown(coid, OrderState.SUBMITTED)
        else:
            # ACKNOWLEDGED or still UNKNOWN — not a resolvable state via
            # the reconciliation path; leave as-is for manual review.
            logger.warning(
                "Order %r remains UNKNOWN after reconciliation — "
                "broker returned unresolvable status %s.",
                coid,
                new_state.value,
            )

    def _record_fill(
        self,
        order: Order,
        filled_qty: float,
        avg_price: float,
        partial: bool = False,
    ) -> None:
        """Record an ORDER_FILLED audit event for a reconciliation-confirmed fill."""
        if self._audit_ledger is None:
            return
        self._audit_ledger.record(
            action=AuditAction.ORDER_FILLED,
            symbol=order.symbol,
            order_id=order.client_order_id,
            strategy_id=order.strategy_id,
            details={
                "filled_quantity": filled_qty,
                "avg_fill_price": avg_price,
                "partial": partial,
                "source": "reconciliation",
            },
        )

    def _is_too_old(self, order: Order) -> bool:
        """Return True if the order is older than max_reconcile_age_secs."""
        if self._max_age <= 0:
            return False
        age = (datetime.now(timezone.utc) - order.timestamp).total_seconds()
        return bool(age > self._max_age)


class AccountReconciler:
    """Compare platform state with broker ground truth and halt on mismatches."""

    def __init__(
        self,
        broker: BrokerInterface,
        order_manager: OrderManager,
        audit_ledger: AuditLedger,
        kill_switch: KillSwitch,
        account_id: str = "",
        position_tolerance: float = 1e-6,
        cash_tolerance: float = 1.0,
    ) -> None:
        self._broker = broker
        self._order_manager = order_manager
        self._audit_ledger = audit_ledger
        self._kill_switch = kill_switch
        self._account_id = account_id
        self._position_tolerance = position_tolerance
        self._cash_tolerance = cash_tolerance

    def reconcile(
        self,
        expected_positions: Dict[str, float],
        expected_cash: Optional[float] = None,
    ) -> dict:
        """Run broker/account reconciliation and activate kill switch on mismatch."""
        broker_positions = {
            p["symbol"]: float(p.get("quantity", 0.0) or 0.0)
            for p in self._broker.get_positions(self._account_id)
        }
        open_orders = self._broker.get_open_orders(self._account_id)
        mismatches = []
        symbols = set(expected_positions).union(broker_positions)
        for symbol in sorted(symbols):
            expected = float(expected_positions.get(symbol, 0.0) or 0.0)
            actual = float(broker_positions.get(symbol, 0.0) or 0.0)
            if abs(expected - actual) > self._position_tolerance:
                mismatches.append({
                    "type": "position",
                    "symbol": symbol,
                    "expected": expected,
                    "actual": actual,
                })

        account = self._broker.get_account_info(self._account_id)
        if expected_cash is not None:
            cash = float(account.get("cash_balance", 0.0) or 0.0)
            if abs(float(expected_cash) - cash) > self._cash_tolerance:
                mismatches.append({
                    "type": "cash",
                    "expected": float(expected_cash),
                    "actual": cash,
                })

        tracked_broker_ids = {
            o.broker_order_id for o in self._order_manager.active_orders() if o.broker_order_id
        }
        for open_order in open_orders:
            broker_id = str(open_order.get("order_id", ""))
            if broker_id and broker_id not in tracked_broker_ids:
                mismatches.append({
                    "type": "open_order",
                    "broker_order_id": broker_id,
                    "symbol": open_order.get("symbol"),
                    "status": open_order.get("status"),
                })

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker_positions": broker_positions,
            "expected_positions": expected_positions,
            "open_orders": open_orders,
            "mismatches": mismatches,
            "ok": not mismatches,
        }
        self._audit_ledger.record(
            action=AuditAction.RECONCILIATION_RUN,
            details=report,
        )
        if mismatches:
            self._kill_switch.activate(
                KillSwitchReason.POSITION_MISMATCH,
                detail=f"Account reconciliation mismatches: {mismatches}",
            )
            self._audit_ledger.record(
                action=AuditAction.KILL_SWITCH_TRIGGERED,
                details={"reason": "POSITION_MISMATCH", "mismatches": mismatches},
            )
        return report
