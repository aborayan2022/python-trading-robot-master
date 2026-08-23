"""Paper trading broker simulator - no external API calls."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pyrobot.brokers.base import BrokerInterface
from pyrobot.logging_config import get_logger

logger = get_logger("paper")

_BUY_INSTRUCTIONS = ("BUY", "BUY_TO_COVER")
_SELL_INSTRUCTIONS = ("SELL", "SELL_SHORT")


class PaperBroker(BrokerInterface):
    """Local paper trading simulator.

    Simulates order execution against provided price data without
    making any external API calls. Tracks virtual portfolio, long and
    short positions, realized P&L, and order history.

    Fill model:
        - MARKET orders fill immediately at the last known price.
        - LIMIT orders only fill when the market price crosses the
          limit (buy: last <= limit, sell: last >= limit); otherwise
          they rest as open orders.
        - STOP orders only fill when the market price crosses the stop
          (buy stop: last >= stop, sell stop: last <= stop); otherwise
          they rest as open orders.
        - Open orders are re-evaluated every time ``update_prices`` is
          called and may be cancelled via ``cancel_order``.

    Useful for:
        - Testing strategies without a broker account
        - Development and debugging
        - Backtesting with realistic execution flow
    """

    def __init__(
        self,
        initial_balance: float = 100000.0,
        commission_per_trade: float = 0.0,
        **kwargs,
    ) -> None:
        self._initial_balance = initial_balance
        self._cash_balance = initial_balance
        self._commission_per_trade = commission_per_trade
        self._positions: Dict[str, dict] = {}
        self._short_positions: Dict[str, dict] = {}
        self._open_orders: Dict[str, dict] = {}
        self._orders: List[dict] = []
        self._order_history: List[dict] = []
        self._current_prices: Dict[str, dict] = {}
        self._realized_pnl = 0.0
        self._authenticated = False

    @property
    def name(self) -> str:
        return "paper"

    def authenticate(self) -> bool:
        self._authenticated = True
        logger.info(
            f"Paper broker initialized with balance: ${self._initial_balance:,.2f}"
        )
        return True

    def update_prices(self, prices: Dict[str, dict]) -> None:
        """Update market prices, then re-evaluate all open orders.

        Any resting LIMIT/STOP order whose condition is met by the new
        prices is filled at the new market price.
        """
        self._current_prices.update(prices)
        self._process_open_orders()

    def get_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        quotes = {}
        for symbol in symbols:
            if symbol in self._current_prices:
                price_data = self._current_prices[symbol]
                quotes[symbol] = {
                    "symbol": symbol,
                    "last_price": price_data.get("close", price_data.get("last_price", 0.0)),
                    "bid": price_data.get("bid", price_data.get("close", 0.0)),
                    "ask": price_data.get("ask", price_data.get("close", 0.0)),
                    "open": price_data.get("open", 0.0),
                    "high": price_data.get("high", 0.0),
                    "low": price_data.get("low", 0.0),
                    "volume": price_data.get("volume", 0),
                }
            else:
                quotes[symbol] = {
                    "symbol": symbol,
                    "last_price": 0.0,
                    "bid": 0.0,
                    "ask": 0.0,
                    "open": 0.0,
                    "high": 0.0,
                    "low": 0.0,
                    "volume": 0,
                }
        return quotes

    def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        bar_size: int = 1,
        bar_type: str = "minute",
    ) -> List[dict]:
        return []

    def place_order(self, account: str, order: dict) -> dict:
        """Submit an order to the paper broker.

        MARKET orders fill immediately. LIMIT and STOP orders only
        fill if their condition is met by the current price; otherwise
        they are registered as open orders (status ``OPEN``) that are
        re-evaluated on every ``update_prices`` call.
        """
        order_id = str(uuid.uuid4())[:8]

        symbol = ""
        quantity = 0
        instruction = ""
        order_type = order.get("orderType", "MARKET").upper()

        if "orderLegCollection" in order and order["orderLegCollection"]:
            leg = order["orderLegCollection"][0]
            instruction = leg.get("instruction", "BUY").upper()
            quantity = leg.get("quantity", 0)
            instrument = leg.get("instrument", {})
            symbol = instrument.get("symbol", "")

        last_price = self._last_price(symbol)

        if last_price is None:
            logger.warning(
                f"Order {order_id} for {symbol}: no price available, rejecting"
            )
            return {
                "order_id": order_id,
                "status": "REJECTED",
                "request_body": order,
            }

        record = {
            "order_id": order_id,
            "symbol": symbol,
            "instruction": instruction,
            "quantity": quantity,
            "order_type": order_type,
            "limit_price": order.get("price", 0.0),
            "stop_price": order.get("stopPrice", 0.0),
            "status": "OPEN",
            "fill_price": None,
            "filled_quantity": 0,
            "avg_fill_price": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "request_body": order,
        }
        self._order_history.append(record)

        if self._try_execute(record, last_price):
            status = record["status"]
        else:
            self._open_orders[order_id] = record
            status = "OPEN"

        logger.info(
            f"Order {order_id}: {instruction} {quantity} {symbol} "
            f"({order_type}) -> {status}"
        )

        return {
            "order_id": order_id,
            "status": status,
            "request_body": order,
        }

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Only resting (unfilled) LIMIT/STOP orders can be cancelled.
        MARKET orders fill instantly and filled/rejected/unknown order
        ids cannot be cancelled.
        """
        record = self._open_orders.pop(order_id, None)
        if record is None:
            logger.warning(
                f"Cancel failed for order {order_id}: not an open order"
            )
            return False

        record["status"] = "CANCELLED"
        record["cancelled_at"] = datetime.now(timezone.utc).isoformat()
        self._orders.append(record)
        logger.info(f"Order {order_id}: CANCELLED")
        return True

    def get_open_orders(self, account: Optional[str] = None) -> List[dict]:
        """Return all resting (unfilled) orders."""
        return [
            {
                "order_id": record["order_id"],
                "symbol": record["symbol"],
                "instruction": record["instruction"],
                "quantity": record["quantity"],
                "order_type": record["order_type"],
                "status": record["status"],
            }
            for record in self._open_orders.values()
        ]

    def _last_price(self, symbol: str) -> Optional[float]:
        """Return the last known price for a symbol, None if unknown."""
        price_data = self._current_prices.get(symbol)
        if price_data is None:
            return None
        price = price_data.get("close", price_data.get("last_price", 0.0))
        return float(price) if price else None

    def _try_execute(self, record: dict, last_price: float) -> bool:
        """Attempt to execute an order record against ``last_price``.

        Returns True when the order reached a terminal state (FILLED
        or REJECTED), False when it should rest as an open order.
        """
        instruction = record["instruction"]
        order_type = record["order_type"]

        if instruction not in _BUY_INSTRUCTIONS + _SELL_INSTRUCTIONS:
            record["status"] = "REJECTED"
            logger.warning(
                f"Order {record['order_id']}: unknown instruction "
                f"{instruction!r}, rejecting"
            )
            return True

        is_buy = instruction in _BUY_INSTRUCTIONS
        limit_price = float(record.get("limit_price") or 0.0)
        stop_price = float(record.get("stop_price") or 0.0)
        if order_type == "LIMIT" and not limit_price:
            limit_price = last_price
        if order_type in ("STOP", "STOP_LIMIT") and not stop_price:
            stop_price = last_price

        fill_price = last_price
        if order_type == "LIMIT":
            if is_buy and last_price > limit_price:
                return False
            if not is_buy and last_price < limit_price:
                return False
            fill_price = min(limit_price, last_price) if is_buy else max(
                limit_price, last_price
            )
        elif order_type in ("STOP", "STOP_LIMIT"):
            if is_buy and last_price < stop_price:
                return False
            if not is_buy and last_price > stop_price:
                return False
            # Fill at the stop price or worse (gap through the stop).
            fill_price = max(stop_price, last_price) if is_buy else min(
                stop_price, last_price
            )
            if order_type == "STOP_LIMIT" and limit_price:
                fill_price = limit_price

        error = self._apply_fill(
            symbol=record["symbol"],
            instruction=instruction,
            quantity=record["quantity"],
            price=fill_price,
        )
        if error is not None:
            record["status"] = "REJECTED"
            logger.warning(f"Order {record['order_id']}: rejected ({error})")
            return True

        record["status"] = "FILLED"
        record["fill_price"] = fill_price
        record["filled_quantity"] = record["quantity"]
        record["avg_fill_price"] = fill_price
        record["filled_at"] = datetime.now(timezone.utc).isoformat()
        self._orders.append(record)
        logger.info(
            f"Order {record['order_id']}: {instruction} "
            f"{record['quantity']} {record['symbol']} "
            f"@ ${fill_price:.2f} (FILLED)"
        )
        return True

    def _apply_fill(
        self, symbol: str, instruction: str, quantity: int, price: float
    ) -> Optional[str]:
        """Apply a fill to cash and position books.

        Returns None on success or a rejection reason string.
        """
        commission = self._commission_per_trade

        if instruction == "BUY":
            cost = price * quantity + commission
            if cost > self._cash_balance:
                return (
                    f"insufficient funds "
                    f"(need ${cost:,.2f}, have ${self._cash_balance:,.2f})"
                )
            self._cash_balance -= cost
            self._add_long(symbol=symbol, quantity=quantity, price=price)
            return None

        if instruction == "BUY_TO_COVER":
            short = self._short_positions.get(symbol)
            if short is None or short["quantity"] <= 0:
                return f"no short position in {symbol} to cover"
            if quantity > short["quantity"]:
                return (
                    f"short quantity {short['quantity']} in {symbol} "
                    f"is less than order quantity {quantity}"
                )
            cost = price * quantity + commission
            if cost > self._cash_balance:
                return (
                    f"insufficient funds "
                    f"(need ${cost:,.2f}, have ${self._cash_balance:,.2f})"
                )
            self._cash_balance -= cost
            self._realized_pnl += (short["average_price"] - price) * quantity
            short["quantity"] -= quantity
            if short["quantity"] <= 0:
                del self._short_positions[symbol]
            return None

        # SELL / SELL_SHORT: close long holdings first, then short the
        # remaining quantity (a SELL beyond holdings shorts the excess).
        remaining = quantity
        if instruction == "SELL":
            long_position = self._positions.get(symbol)
            if long_position is not None:
                close_qty = min(long_position["quantity"], remaining)
                if close_qty > 0:
                    self._cash_balance += price * close_qty
                    self._realized_pnl += (
                        price - long_position["average_price"]
                    ) * close_qty
                    long_position["quantity"] -= close_qty
                    if long_position["quantity"] <= 0:
                        del self._positions[symbol]
                    remaining -= close_qty

        if remaining > 0:
            self._open_short(symbol=symbol, quantity=remaining, price=price)
            self._cash_balance += price * remaining
        if quantity > 0:
            self._cash_balance -= commission
        return None

    def _add_long(self, symbol: str, quantity: int, price: float) -> None:
        """Add to (or open) a long position at ``price``."""
        if quantity <= 0:
            return
        position = self._positions.get(symbol)
        if position is None:
            self._positions[symbol] = {
                "symbol": symbol,
                "quantity": quantity,
                "average_price": price,
                "market_value": 0.0,
                "asset_type": "EQUITY",
            }
        else:
            old_qty = position["quantity"]
            new_qty = old_qty + quantity
            position["average_price"] = (
                position["average_price"] * old_qty + price * quantity
            ) / new_qty
            position["quantity"] = new_qty

    def _open_short(self, symbol: str, quantity: int, price: float) -> None:
        """Open (or increase) a short position at ``price``."""
        if quantity <= 0:
            return
        short = self._short_positions.get(symbol)
        if short is None:
            self._short_positions[symbol] = {
                "symbol": symbol,
                "quantity": quantity,
                "average_price": price,
                "asset_type": "EQUITY",
            }
        else:
            old_qty = short["quantity"]
            new_qty = old_qty + quantity
            short["average_price"] = (
                short["average_price"] * old_qty + price * quantity
            ) / new_qty
            short["quantity"] = new_qty

    def _process_open_orders(self) -> None:
        """Re-evaluate all resting orders against current prices."""
        for order_id, record in list(self._open_orders.items()):
            last_price = self._last_price(record["symbol"])
            if last_price is None:
                continue
            if self._try_execute(record, last_price):
                self._open_orders.pop(order_id, None)

    def get_order_status(self, account: str, order_id: str) -> dict:
        """Get the status of an order.

        Returns a dict with keys:
            {'order_id', 'status', 'quantity', 'filled_quantity',
             'avg_fill_price', 'remaining_quantity'}
        """
        record = None
        for order in reversed(self._order_history):
            if order["order_id"] == order_id:
                record = order
                break

        if record is None:
            return {
                "order_id": order_id,
                "status": "UNKNOWN",
                "quantity": 0,
                "filled_quantity": 0,
                "avg_fill_price": 0.0,
                "remaining_quantity": 0,
            }

        filled = record.get("filled_quantity", 0)
        return {
            "order_id": order_id,
            "status": record["status"],
            "quantity": record["quantity"],
            "filled_quantity": filled,
            "avg_fill_price": record.get("avg_fill_price", 0.0),
            "remaining_quantity": max(record["quantity"] - filled, 0),
        }

    def _market_value(self, positions: Dict[str, dict]) -> float:
        """Compute the market value of a position book."""
        return float(
            sum(
                position["quantity"]
                * self._current_prices.get(position["symbol"], {}).get("close", 0.0)
                for position in positions.values()
            )
        )

    def get_account_info(self, account: str = None) -> dict:
        """Get account information including short exposure.

        equity = cash + long market value - short liability, where the
        short liability is short quantity times the current price.
        """
        long_value = self._market_value(self._positions)
        short_value = self._market_value(self._short_positions)
        return {
            "account_number": "PAPER_ACCOUNT",
            "cash_balance": self._cash_balance,
            "buying_power": self._cash_balance,
            "long_market_value": long_value,
            "short_market_value": short_value,
            "equity": self._cash_balance + long_value - short_value,
        }

    def get_positions(self, account: str = None) -> List[dict]:
        """Get all positions; shorts are reported with negative quantity."""
        result = []
        for position in self._positions.values():
            current_price = self._current_prices.get(position["symbol"], {}).get(
                "close", position["average_price"]
            )
            result.append(
                {
                    "symbol": position["symbol"],
                    "quantity": position["quantity"],
                    "average_price": position["average_price"],
                    "market_value": position["quantity"] * current_price,
                    "asset_type": position["asset_type"],
                }
            )
        for short in self._short_positions.values():
            current_price = self._current_prices.get(short["symbol"], {}).get(
                "close", short["average_price"]
            )
            result.append(
                {
                    "symbol": short["symbol"],
                    "quantity": -short["quantity"],
                    "average_price": short["average_price"],
                    "market_value": -short["quantity"] * current_price,
                    "asset_type": short["asset_type"],
                }
            )
        return result

    def get_option_chain(self, symbol: str) -> dict:
        return {"symbol": symbol, "expirations": [], "strikes": []}

    @property
    def portfolio_summary(self) -> dict:
        long_value = self._market_value(self._positions)
        short_value = self._market_value(self._short_positions)
        total_value = self._cash_balance + long_value - short_value
        return {
            "initial_balance": self._initial_balance,
            "cash_balance": self._cash_balance,
            "market_value": long_value,
            "short_market_value": short_value,
            "realized_pnl": self._realized_pnl,
            "total_value": total_value,
            "total_pnl": total_value - self._initial_balance,
            "total_pnl_pct": (
                (total_value - self._initial_balance) / self._initial_balance * 100
                if self._initial_balance > 0
                else 0.0
            ),
            "positions_count": len(self._positions) + len(self._short_positions),
            "orders_count": len(self._orders),
        }

    @property
    def order_history(self) -> List[dict]:
        return list(self._order_history)
