"""Canonical Position model."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PositionSide(Enum):
    """Position side."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


@dataclass
class Position:
    """Canonical position model for tracking holdings.

    Attributes:
        symbol: Ticker symbol.
        side: Long, short, or flat.
        quantity: Number of shares/units (positive for long, negative for short).
        avg_entry_price: Average price at which position was opened.
        current_price: Latest market price.
        market_value: Current market value of the position.
        unrealized_pnl: Unrealized profit/loss.
        realized_pnl: Realized profit/loss from partial closes.
        opened_at: When the position was first opened.
        updated_at: When the position was last updated.
        strategy_id: Strategy that owns this position.
        sector: Sector classification.
        asset_type: Type of asset (EQUITY, ETF, OPTION, etc.).
    """

    symbol: str
    side: PositionSide = PositionSide.FLAT
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    opened_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_id: Optional[str] = None
    sector: Optional[str] = None
    asset_type: str = "EQUITY"

    @property
    def is_open(self) -> bool:
        """Check if position has any quantity."""
        return abs(self.quantity) > 0

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.side == PositionSide.LONG and self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.side == PositionSide.SHORT and self.quantity < 0

    @property
    def cost_basis(self) -> float:
        """Calculate total cost basis of the position."""
        return abs(self.quantity) * self.avg_entry_price

    def update_market_value(self, current_price: float) -> None:
        """Update market value and unrealized P&L based on current price."""
        self.current_price = current_price
        self.market_value = self.quantity * current_price
        self.unrealized_pnl = (current_price - self.avg_entry_price) * self.quantity
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "avg_entry_price": self.avg_entry_price,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "updated_at": self.updated_at.isoformat(),
            "strategy_id": self.strategy_id,
            "sector": self.sector,
            "asset_type": self.asset_type,
        }

    @classmethod
    def from_broker_dict(cls, broker_dict: dict) -> "Position":
        """Create a Position from broker response dict.

        Handles common broker response formats.
        """
        quantity = broker_dict.get("quantity", 0)
        side = PositionSide.LONG if quantity > 0 else (
            PositionSide.SHORT if quantity < 0 else PositionSide.FLAT
        )

        return cls(
            symbol=broker_dict.get("symbol", ""),
            side=side,
            quantity=quantity,
            avg_entry_price=broker_dict.get("average_price", 0),
            current_price=broker_dict.get("last_price", 0),
            market_value=broker_dict.get("market_value", 0),
            asset_type=broker_dict.get("asset_type", "EQUITY"),
        )
