"""Paper trading broker simulator - no external API calls."""

import uuid

from datetime import datetime
from typing import Dict
from typing import List

from pyrobot.brokers.base import BrokerInterface
from pyrobot.logging_config import get_logger

logger = get_logger("paper")


class PaperBroker(BrokerInterface):
    """Local paper trading simulator.

    Simulates order execution against provided price data without
    making any external API calls. Tracks virtual portfolio, P&L,
    and order history.

    Useful for:
        - Testing strategies without a broker account
        - Development and debugging
        - Backtesting with realistic execution flow
    """

    def __init__(self, initial_balance: float = 100000.0, **kwargs) -> None:
        self._initial_balance = initial_balance
        self._cash_balance = initial_balance
        self._positions: Dict[str, dict] = {}
        self._orders: List[dict] = []
        self._order_history: List[dict] = []
        self._current_prices: Dict[str, dict] = {}
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
        self._current_prices.update(prices)

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
        order_id = str(uuid.uuid4())[:8]

        symbol = ""
        quantity = 0
        instruction = ""
        order_type = order.get("orderType", "MARKET")

        if "orderLegCollection" in order and order["orderLegCollection"]:
            leg = order["orderLegCollection"][0]
            instruction = leg.get("instruction", "BUY")
            quantity = leg.get("quantity", 0)
            instrument = leg.get("instrument", {})
            symbol = instrument.get("symbol", "")

        fill_price = self._get_fill_price(symbol, order, order_type)

        if fill_price is None:
            logger.warning(
                f"Order {order_id} for {symbol}: no price available, rejecting"
            )
            return {
                "order_id": order_id,
                "status": "REJECTED",
                "request_body": order,
            }

        is_buy = instruction in ("BUY", "BUY_TO_COVER")
        is_sell = instruction in ("SELL", "SELL_SHORT")

        if is_buy:
            cost = fill_price * quantity
            if cost > self._cash_balance:
                logger.warning(
                    f"Order {order_id}: insufficient funds "
                    f"(need ${cost:,.2f}, have ${self._cash_balance:,.2f})"
                )
                return {
                    "order_id": order_id,
                    "status": "REJECTED",
                    "request_body": order,
                }
            self._cash_balance -= cost

            if symbol in self._positions:
                pos = self._positions[symbol]
                old_qty = pos["quantity"]
                old_avg = pos["average_price"]
                new_qty = old_qty + quantity
                pos["average_price"] = (
                    (old_avg * old_qty + fill_price * quantity) / new_qty
                )
                pos["quantity"] = new_qty
            else:
                self._positions[symbol] = {
                    "symbol": symbol,
                    "quantity": quantity,
                    "average_price": fill_price,
                    "market_value": 0.0,
                    "asset_type": "EQUITY",
                }

        elif is_sell:
            if symbol in self._positions:
                pos = self._positions[symbol]
                proceeds = fill_price * quantity
                self._cash_balance += proceeds
                pos["quantity"] -= quantity
                if pos["quantity"] <= 0:
                    del self._positions[symbol]
            else:
                proceeds = fill_price * quantity
                self._cash_balance += proceeds

        order_record = {
            "order_id": order_id,
            "symbol": symbol,
            "instruction": instruction,
            "quantity": quantity,
            "fill_price": fill_price,
            "order_type": order_type,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._orders.append(order_record)
        self._order_history.append(order_record)

        logger.info(
            f"Order {order_id}: {instruction} {quantity} {symbol} "
            f"@ ${fill_price:.2f} (FILLED)"
        )

        return {
            "order_id": order_id,
            "status": "FILLED",
            "request_body": order,
        }

    def _get_fill_price(
        self, symbol: str, order: dict, order_type: str
    ) -> float:
        if symbol not in self._current_prices:
            return None

        price_data = self._current_prices[symbol]
        last_price = price_data.get("close", price_data.get("last_price", 0.0))

        if order_type == "MARKET":
            return last_price
        elif order_type == "LIMIT":
            return order.get("price", last_price)
        elif order_type == "STOP":
            return order.get("stopPrice", last_price)
        elif order_type == "STOP_LIMIT":
            return order.get("stopPrice", last_price)

        return last_price

    def get_order_status(self, account: str, order_id: str) -> dict:
        for order in reversed(self._orders):
            if order["order_id"] == order_id:
                return {
                    "order_id": order_id,
                    "status": "FILLED",
                    "filled_quantity": order["quantity"],
                    "remaining_quantity": 0,
                }
        return {
            "order_id": order_id,
            "status": "UNKNOWN",
            "filled_quantity": 0,
            "remaining_quantity": 0,
        }

    def get_account_info(self, account: str = None) -> dict:
        total_market_value = sum(
            pos["quantity"]
            * self._current_prices.get(pos["symbol"], {}).get("close", 0.0)
            for pos in self._positions.values()
        )
        return {
            "account_number": "PAPER_ACCOUNT",
            "cash_balance": self._cash_balance,
            "buying_power": self._cash_balance,
            "long_market_value": total_market_value,
            "short_market_value": 0.0,
        }

    def get_positions(self, account: str = None) -> List[dict]:
        result = []
        for pos in self._positions.values():
            current_price = self._current_prices.get(pos["symbol"], {}).get(
                "close", pos["average_price"]
            )
            result.append(
                {
                    "symbol": pos["symbol"],
                    "quantity": pos["quantity"],
                    "average_price": pos["average_price"],
                    "market_value": pos["quantity"] * current_price,
                    "asset_type": pos["asset_type"],
                }
            )
        return result

    def get_option_chain(self, symbol: str) -> dict:
        return {"symbol": symbol, "expirations": [], "strikes": []}

    @property
    def portfolio_summary(self) -> dict:
        total_market_value = sum(
            pos["quantity"]
            * self._current_prices.get(pos["symbol"], {}).get("close", 0.0)
            for pos in self._positions.values()
        )
        total_value = self._cash_balance + total_market_value
        return {
            "initial_balance": self._initial_balance,
            "cash_balance": self._cash_balance,
            "market_value": total_market_value,
            "total_value": total_value,
            "total_pnl": total_value - self._initial_balance,
            "total_pnl_pct": (
                (total_value - self._initial_balance) / self._initial_balance * 100
                if self._initial_balance > 0
                else 0.0
            ),
            "positions_count": len(self._positions),
            "orders_count": len(self._orders),
        }

    @property
    def order_history(self) -> List[dict]:
        return list(self._order_history)
