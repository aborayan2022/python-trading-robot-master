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
from typing import List, Optional

from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import BrokerError, ReconciliationError
from pyrobot.execution.order_manager import OrderManager
from pyrobot.logging_config import get_logger
from pyrobot.models.order import Order, OrderState

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
    """

    def __init__(
        self,
        order_manager: OrderManager,
        broker: BrokerInterface,
        account_id: str = "",
        max_reconcile_age_secs: float = 86_400,  # 24 hours
    ) -> None:
        self._order_manager = order_manager
        self._broker = broker
        self._account_id = account_id
        self._max_age = max_reconcile_age_secs

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
        """Apply the reconciled state to the order via OrderManager."""
        coid = order.client_order_id

        # Force override the UNKNOWN state to the reconciled state by
        # temporarily setting the order status to allow the transition.
        # The OrderManager's _transition validates UNKNOWN → X transitions
        # only if listed; we patch the order directly for reconciliation.
        order.status = OrderState.SUBMITTED  # Unlock from UNKNOWN

        if new_state == OrderState.FILLED:
            self._order_manager.mark_filled(coid, filled_qty, avg_price)
        elif new_state == OrderState.PARTIALLY_FILLED:
            self._order_manager.mark_partially_filled(coid, filled_qty, avg_price)
        elif new_state == OrderState.CANCELLED:
            self._order_manager.mark_cancelled(coid)
        elif new_state == OrderState.REJECTED:
            self._order_manager.mark_rejected(coid, reason="reconciled from broker")
        elif new_state == OrderState.ACKNOWLEDGED:
            self._order_manager.mark_acknowledged(coid)
        else:
            # Still UNKNOWN — reset and log
            order.status = OrderState.UNKNOWN
            logger.warning(
                "Order %r remains UNKNOWN after reconciliation — "
                "broker returned unresolvable status.",
                coid,
            )

    def _is_too_old(self, order: Order) -> bool:
        """Return True if the order is older than max_reconcile_age_secs."""
        if self._max_age <= 0:
            return False
        age = (datetime.now(timezone.utc) - order.timestamp).total_seconds()
        return age > self._max_age
