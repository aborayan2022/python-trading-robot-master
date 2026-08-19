"""Canonical Order model with lifecycle states."""

import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class OrderState(Enum):
    """Order lifecycle states."""

    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class OrderSide(Enum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"
    SELL_SHORT = "SELL_SHORT"
    BUY_TO_COVER = "BUY_TO_COVER"


class OrderType(Enum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"


class TimeInForce(Enum):
    """Time-in-force instructions."""

    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"


@dataclass
class Order:
    """Canonical order model used across all broker adapters.

    This is the single source of truth for order representation.
    Broker adapters must convert to/from this model.

    Attributes:
        symbol: Ticker symbol (e.g., 'AAPL').
        side: Buy or sell side.
        quantity: Number of shares/units.
        order_type: Type of order (market, limit, etc.).
        limit_price: Limit price for limit orders.
        stop_price: Stop price for stop orders.
        time_in_force: How long the order remains active.
        strategy_id: Identifier of the strategy that generated this order.
        signal_id: Identifier of the signal that triggered this order.
        client_order_id: Unique client-generated ID for idempotency.
        timestamp: When the order was created (UTC).
        broker_order_id: Broker-assigned order ID after submission.
        status: Current order lifecycle state.
        filled_quantity: Quantity that has been filled.
        avg_fill_price: Average fill price.
        parent_order_id: For child orders (take-profit, stop-loss).
        trailing_distance: Distance for trailing stop orders.
    """

    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    strategy_id: Optional[str] = None
    signal_id: Optional[str] = None
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    broker_order_id: Optional[str] = None
    status: OrderState = OrderState.NEW
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    parent_order_id: Optional[str] = None
    trailing_distance: Optional[float] = None

    @property
    def is_active(self) -> bool:
        """Check if the order is in an active state."""
        return self.status in {
            OrderState.NEW,
            OrderState.SUBMITTED,
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
        }

    @property
    def is_terminal(self) -> bool:
        """Check if the order is in a terminal state."""
        return self.status in {
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
        }

    @property
    def remaining_quantity(self) -> float:
        """Calculate remaining quantity to fill."""
        return self.quantity - self.filled_quantity

    def to_legacy_dict(self) -> dict:
        """Convert to legacy order dict format for backward compatibility.

        Returns a dict matching the orderLegCollection structure used
        by existing broker adapters.
        """
        side_str = self.side.value
        order_type_str = self.order_type.value

        result = {
            "orderType": order_type_str,
            "orderLegCollection": [
                {
                    "instruction": side_str,
                    "quantity": self.quantity,
                    "instrument": {
                        "symbol": self.symbol,
                        "assetType": "EQUITY",
                    },
                }
            ],
            "symbol": self.symbol,
        }

        if self.limit_price is not None:
            result["price"] = self.limit_price

        if self.stop_price is not None:
            result["stopPrice"] = self.stop_price

        if self.client_order_id:
            result["clientOrderId"] = self.client_order_id

        return result

    @classmethod
    def from_legacy_dict(cls, order_dict: dict) -> "Order":
        """Create an Order from a legacy order dict.

        Handles both orderLegCollection format and flat format.
        """
        symbol = ""
        side = OrderSide.BUY
        quantity = 0.0

        if "orderLegCollection" in order_dict and order_dict["orderLegCollection"]:
            leg = order_dict["orderLegCollection"][0]
            instruction = leg.get("instruction", "BUY")
            side = OrderSide(instruction)
            quantity = leg.get("quantity", 0)
            instrument = leg.get("instrument", {})
            symbol = instrument.get("symbol", "")

        if not symbol:
            symbol = order_dict.get("symbol", "")

        order_type_str = order_dict.get("orderType", "MARKET")
        try:
            order_type = OrderType(order_type_str)
        except ValueError:
            order_type = OrderType.MARKET

        return cls(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=order_dict.get("price"),
            stop_price=order_dict.get("stopPrice"),
            client_order_id=order_dict.get("clientOrderId", str(uuid.uuid4())),
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "time_in_force": self.time_in_force.value,
            "strategy_id": self.strategy_id,
            "signal_id": self.signal_id,
            "client_order_id": self.client_order_id,
            "timestamp": self.timestamp.isoformat(),
            "broker_order_id": self.broker_order_id,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "avg_fill_price": self.avg_fill_price,
            "parent_order_id": self.parent_order_id,
            "trailing_distance": self.trailing_distance,
        }
