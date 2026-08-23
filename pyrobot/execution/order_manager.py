"""Order Manager — tracks the full lifecycle of every order.

Responsibilities:
    - Create orders with guaranteed unique client_order_id (idempotency).
    - Track all in-flight orders in memory.
    - Update order state transitions.
    - Detect and reject duplicate orders.
    - Provide snapshots for reconciliation.

Order lifecycle state machine::

    NEW
     └─► SUBMITTED
          └─► ACKNOWLEDGED
               ├─► PARTIALLY_FILLED ──► FILLED
               ├─► CANCEL_PENDING   ──► CANCELLED
               ├─► REJECTED
               └─► EXPIRED

    SUBMITTED / ACKNOWLEDGED / PARTIALLY_FILLED ──► CANCEL_PENDING ──► CANCELLED

    Any state may transition to UNKNOWN if the broker response is ambiguous.
    UNKNOWN orders require explicit reconciliation (see ``resolve_unknown``)
    before being resolved to a reconciled state.
"""

import threading
import uuid
from typing import Dict, List, Optional

from pyrobot.exceptions import (
    DuplicateOrderError,
    OrderStateError,
)
from pyrobot.logging_config import get_logger
from pyrobot.models.order import Order, OrderSide, OrderState, OrderType, TimeInForce
from pyrobot.models.signal import Signal, SignalAction

logger = get_logger("order_manager")

# States an UNKNOWN order may be reconciled into via resolve_unknown().
_RECONCILABLE_STATES: frozenset = frozenset({
    OrderState.SUBMITTED,
    OrderState.PARTIALLY_FILLED,
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
})

# Valid forward state transitions.  UNKNOWN is reachable from any state.
_VALID_TRANSITIONS: Dict[OrderState, frozenset] = {
    OrderState.NEW: frozenset({
        OrderState.SUBMITTED, OrderState.REJECTED, OrderState.CANCELLED,
        OrderState.UNKNOWN,
    }),
    OrderState.SUBMITTED: frozenset({
        OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.CANCELLED,
        OrderState.CANCEL_PENDING,
        OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.UNKNOWN,
    }),
    OrderState.ACKNOWLEDGED: frozenset({
        OrderState.PARTIALLY_FILLED, OrderState.FILLED,
        OrderState.CANCEL_PENDING, OrderState.CANCELLED,
        OrderState.REJECTED, OrderState.EXPIRED, OrderState.UNKNOWN,
    }),
    OrderState.PARTIALLY_FILLED: frozenset({
        OrderState.FILLED, OrderState.CANCEL_PENDING,
        OrderState.CANCELLED, OrderState.UNKNOWN,
    }),
    OrderState.CANCEL_PENDING: frozenset({
        OrderState.CANCELLED, OrderState.FILLED, OrderState.UNKNOWN,
    }),
    # Terminal states — no further transitions except UNKNOWN (broker error)
    OrderState.FILLED: frozenset({OrderState.UNKNOWN}),
    OrderState.CANCELLED: frozenset({OrderState.UNKNOWN}),
    OrderState.REJECTED: frozenset({OrderState.UNKNOWN}),
    OrderState.EXPIRED: frozenset({OrderState.UNKNOWN}),
    # UNKNOWN is only resolvable via explicit reconciliation
    # (OrderManager.resolve_unknown) — never by a regular forward transition.
    OrderState.UNKNOWN: _RECONCILABLE_STATES,
}

# Map from SignalAction to OrderSide
_ACTION_TO_SIDE: Dict[SignalAction, OrderSide] = {
    SignalAction.BUY: OrderSide.BUY,
    SignalAction.SELL: OrderSide.SELL,
    SignalAction.SELL_SHORT: OrderSide.SELL_SHORT,
    SignalAction.BUY_TO_COVER: OrderSide.BUY_TO_COVER,
}


class OrderManager:
    """Thread-safe manager for order creation and lifecycle tracking.

    Args:
        max_orders: Maximum number of active (non-terminal) orders allowed
            simultaneously.  Set to 0 to disable the limit.
    """

    def __init__(self, max_orders: int = 500) -> None:
        self._orders: Dict[str, Order] = {}       # client_order_id → Order
        self._broker_id_map: Dict[str, str] = {}  # broker_order_id → client_order_id
        self._max_orders = max_orders
        self._lock = threading.RLock()

    # ── Factory ───────────────────────────────────────────────────────────────

    def create_from_signal(
        self,
        signal: Signal,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """Create and register an Order from a Signal.

        Args:
            signal: The originating Signal (must be actionable).
            quantity: Number of shares / units.
            order_type: MARKET, LIMIT, STOP, etc.
            limit_price: Required for LIMIT / STOP_LIMIT orders.
            stop_price: Required for STOP / STOP_LIMIT orders.
            time_in_force: DAY, GTC, IOC, etc.
            client_order_id: If provided, used as the idempotency key.
                Defaults to a new UUID.

        Returns:
            The newly created and registered Order.

        Raises:
            ValueError: If the signal is not actionable.
            DuplicateOrderError: If client_order_id already exists.
        """
        if not signal.is_actionable:
            raise ValueError(
                f"Signal action {signal.action} is not actionable — "
                "cannot create an order from HOLD or NO_TRADE signals."
            )

        side = _ACTION_TO_SIDE.get(signal.action)
        if side is None:
            raise ValueError(f"Cannot map signal action {signal.action} to an order side.")

        coid = client_order_id or str(uuid.uuid4())

        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            strategy_id=signal.strategy_id,
            signal_id=signal.signal_id,
            client_order_id=coid,
        )

        self._register(order)
        return order

    def create(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        strategy_id: Optional[str] = None,
        signal_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """Create and register an Order directly (without a Signal).

        Args:
            symbol: Ticker symbol.
            side: BUY / SELL / etc.
            quantity: Number of shares / units.
            order_type: MARKET, LIMIT, STOP, etc.
            limit_price: Required for LIMIT / STOP_LIMIT orders.
            stop_price: Required for STOP / STOP_LIMIT orders.
            time_in_force: DAY, GTC, IOC, etc.
            strategy_id: Optional originating strategy identifier.
            signal_id: Optional originating signal identifier.
            client_order_id: Idempotency key.  Defaults to a new UUID.

        Returns:
            The newly created and registered Order.

        Raises:
            DuplicateOrderError: If client_order_id already exists.
        """
        coid = client_order_id or str(uuid.uuid4())
        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            strategy_id=strategy_id,
            signal_id=signal_id,
            client_order_id=coid,
        )
        self._register(order)
        return order

    def _register(self, order: Order) -> None:
        """Add the order to the internal registry.

        Raises:
            DuplicateOrderError: If client_order_id is already known.
        """
        with self._lock:
            if order.client_order_id in self._orders:
                raise DuplicateOrderError(
                    f"Duplicate order detected: client_order_id={order.client_order_id!r} "
                    "already exists.  This may indicate an API retry or race condition."
                )

            active_count = sum(1 for o in self._orders.values() if o.is_active)
            if self._max_orders > 0 and active_count >= self._max_orders:
                raise RuntimeError(
                    f"Maximum concurrent active orders ({self._max_orders}) reached. "
                    "Cannot create new order."
                )

            self._orders[order.client_order_id] = order
            logger.info(
                "Order registered: coid=%s symbol=%s side=%s qty=%s type=%s",
                order.client_order_id,
                order.symbol,
                order.side.value,
                order.quantity,
                order.order_type.value,
            )

    # ── State transitions ─────────────────────────────────────────────────────

    def mark_submitted(self, client_order_id: str, broker_order_id: str) -> None:
        """Transition order to SUBMITTED and record broker_order_id.

        Args:
            client_order_id: Our internal idempotency key.
            broker_order_id: The broker-assigned order ID returned on submission.

        Raises:
            KeyError: If client_order_id is unknown.
            OrderStateError: If the transition is not valid.
        """
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.SUBMITTED)
            order.broker_order_id = broker_order_id
            self._broker_id_map[broker_order_id] = client_order_id
            logger.info(
                "Order SUBMITTED: coid=%s broker_id=%s",
                client_order_id,
                broker_order_id,
            )

    def mark_acknowledged(self, client_order_id: str) -> None:
        """Transition order to ACKNOWLEDGED."""
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.ACKNOWLEDGED)

    def mark_partially_filled(
        self, client_order_id: str, filled_qty: float, avg_price: float
    ) -> None:
        """Transition order to PARTIALLY_FILLED and update fill data."""
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.PARTIALLY_FILLED)
            order.filled_quantity = filled_qty
            order.avg_fill_price = avg_price
            logger.info(
                "Order PARTIALLY_FILLED: coid=%s filled=%.4f avg_price=%.4f",
                client_order_id, filled_qty, avg_price,
            )

    def mark_filled(
        self, client_order_id: str, filled_qty: float, avg_price: float
    ) -> None:
        """Transition order to FILLED and update fill data."""
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.FILLED)
            order.filled_quantity = filled_qty
            order.avg_fill_price = avg_price
            logger.info(
                "Order FILLED: coid=%s filled=%.4f avg_price=%.4f",
                client_order_id, filled_qty, avg_price,
            )

    def mark_cancelled(self, client_order_id: str) -> None:
        """Transition order to CANCELLED."""
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.CANCELLED)

    def mark_rejected(self, client_order_id: str, reason: str = "") -> None:
        """Transition order to REJECTED."""
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.REJECTED)
            logger.warning(
                "Order REJECTED: coid=%s reason=%r", client_order_id, reason
            )

    def mark_unknown(self, client_order_id: str, reason: str = "") -> None:
        """Transition order to UNKNOWN — requires reconciliation."""
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.UNKNOWN)
            logger.error(
                "Order UNKNOWN: coid=%s reason=%r — reconciliation required.",
                client_order_id, reason,
            )

    def mark_cancel_pending(self, client_order_id: str) -> None:
        """Transition order to CANCEL_PENDING (cancel requested at broker).

        Args:
            client_order_id: Our internal idempotency key.

        Raises:
            KeyError: If client_order_id is unknown.
            OrderStateError: If the transition is not valid.
        """
        with self._lock:
            order = self._get(client_order_id)
            self._transition(order, OrderState.CANCEL_PENDING)
            logger.info(
                "Order CANCEL_PENDING: coid=%s broker_id=%s",
                client_order_id,
                order.broker_order_id,
            )

    def resolve_unknown(
        self,
        client_order_id: str,
        new_state: OrderState,
        filled_qty: float = 0.0,
        avg_price: float = 0.0,
    ) -> None:
        """Resolve an order in UNKNOWN state to its reconciled true state.

        This is the ONLY sanctioned way out of UNKNOWN: the transition is
        validated against the reconcilable-state map and applied under the
        manager's lock, so the state machine is never bypassed.

        Args:
            client_order_id: Our internal idempotency key.
            new_state: The reconciled state.  Must be one of SUBMITTED,
                PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED.
            filled_qty: Filled quantity (applied for fill states).
            avg_price: Average fill price (applied for fill states).

        Raises:
            KeyError: If client_order_id is unknown.
            OrderStateError: If the order is not in UNKNOWN state, or
                ``new_state`` is not a reconcilable state.
        """
        with self._lock:
            order = self._get(client_order_id)

            if order.status != OrderState.UNKNOWN:
                raise OrderStateError(
                    f"resolve_unknown requires current state UNKNOWN for order "
                    f"{client_order_id!r}, got {order.status.value}."
                )

            if new_state not in _RECONCILABLE_STATES:
                raise OrderStateError(
                    f"Cannot resolve UNKNOWN order {client_order_id!r} to "
                    f"{new_state.value}. Allowed: "
                    f"{[s.value for s in _RECONCILABLE_STATES]}"
                )

            self._transition(order, new_state)

            if new_state in (OrderState.PARTIALLY_FILLED, OrderState.FILLED):
                order.filled_quantity = filled_qty
                order.avg_fill_price = avg_price

            logger.info(
                "Order reconciled from UNKNOWN: coid=%s → %s "
                "(filled=%.4f avg_price=%.4f)",
                client_order_id,
                new_state.value,
                filled_qty,
                avg_price,
            )

    # ── Lookups ───────────────────────────────────────────────────────────────

    def get(self, client_order_id: str) -> Optional[Order]:
        """Return the Order for the given client_order_id, or None."""
        with self._lock:
            return self._orders.get(client_order_id)

    def get_by_broker_id(self, broker_order_id: str) -> Optional[Order]:
        """Return the Order for the given broker_order_id, or None."""
        with self._lock:
            coid = self._broker_id_map.get(broker_order_id)
            if coid:
                return self._orders.get(coid)
            return None

    def active_orders(self) -> List[Order]:
        """Return all currently active (non-terminal) orders."""
        with self._lock:
            return [o for o in self._orders.values() if o.is_active]

    def unknown_orders(self) -> List[Order]:
        """Return all orders in UNKNOWN state (require reconciliation)."""
        with self._lock:
            return [
                o for o in self._orders.values()
                if o.status == OrderState.UNKNOWN
            ]

    def all_orders(self) -> List[Order]:
        """Return a snapshot of all tracked orders."""
        with self._lock:
            return list(self._orders.values())

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, client_order_id: str) -> Order:
        order = self._orders.get(client_order_id)
        if order is None:
            raise KeyError(
                f"Order not found: client_order_id={client_order_id!r}"
            )
        return order

    def _transition(self, order: Order, new_state: OrderState) -> None:
        """Validate and apply a state transition.

        Raises:
            OrderStateError: If the transition is not valid.
        """
        allowed = _VALID_TRANSITIONS.get(order.status, frozenset())
        if new_state not in allowed:
            raise OrderStateError(
                f"Invalid state transition for order {order.client_order_id!r}: "
                f"{order.status.value} → {new_state.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        order.status = new_state
