"""Interactive Brokers adapter using ib_insync/ib_async."""

from datetime import datetime
from typing import Dict, List, Optional

from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import AuthenticationError, BrokerError, OrderRejectedError
from pyrobot.logging_config import get_logger

logger = get_logger("ibkr")


class IBKRBroker(BrokerInterface):
    """Interactive Brokers adapter wrapping ib_insync/ib_async.

    Requires:
        pip install python-trading-robot[ibkr]
        TWS or IB Gateway running locally.

    This is the most complex setup but provides the broadest market access.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        **kwargs,
    ) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._ib = None

    @property
    def name(self) -> str:
        return "ibkr"

    def authenticate(self) -> bool:
        """Connect to TWS or IB Gateway."""
        try:
            from ib_insync import IB

            self._ib = IB()
            self._ib.connect(self._host, self._port, clientId=self._client_id)
            logger.info(
                f"Connected to IBKR at {self._host}:{self._port} "
                f"(client_id={self._client_id})"
            )
            return True
        except Exception as e:
            raise AuthenticationError(
                f"Failed to connect to IBKR. Is TWS/Gateway running? {e}"
            ) from e

    def _normalize_contract(self, contract) -> dict:
        """Normalize an IBKR contract/bar to standard format."""
        return {
            "symbol": getattr(contract, "symbol", ""),
            "open": getattr(contract, "open", 0.0),
            "close": getattr(contract, "close", 0.0),
            "high": getattr(contract, "high", 0.0),
            "low": getattr(contract, "low", 0.0),
            "volume": int(getattr(contract, "volume", 0)),
            "datetime": str(getattr(contract, "date", "")),
        }

    def get_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        """Get current quotes from IBKR."""
        try:
            from ib_insync import Stock

            normalized = {}
            for symbol in symbols:
                contract = Stock(symbol, "SMART", "USD")
                self._ib.qualifyContracts(contract)
                ticker = self._ib.reqMktData(contract, snapshot=True)

                normalized[symbol] = {
                    "symbol": symbol,
                    "last_price": float(ticker.last or 0),
                    "bid": float(ticker.bid or 0),
                    "ask": float(ticker.ask or 0),
                    "open": float(ticker.open or 0),
                    "high": float(ticker.high or 0),
                    "low": float(ticker.low or 0),
                    "volume": int(ticker.volume or 0),
                }

                self._ib.cancelMktData(contract)

            return normalized
        except Exception as e:
            raise BrokerError(f"Failed to get quotes from IBKR: {e}") from e

    def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        bar_size: int = 1,
        bar_type: str = "minute",
    ) -> List[dict]:
        """Get historical prices from IBKR."""
        try:
            from ib_insync import Stock

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            duration_map = {
                "minute": f"{max(1, (end - start).days)} D",
                "hour": f"{max(1, (end - start).days // 7)} W",
                "day": f"{max(1, (end - start).days // 30)} M",
            }

            bar_size_map = {
                "minute": f"{bar_size} min",
                "hour": f"{bar_size} hour",
                "day": f"{bar_size} day",
            }

            bars = self._ib.reqHistoricalData(
                contract,
                endDateTime=end.strftime("%Y%m%d %H:%M:%S"),
                durationStr=duration_map.get(bar_type, "1 D"),
                barSizeSetting=bar_size_map.get(bar_type, "1 min"),
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )

            candles = []
            for bar in bars:
                candles.append(
                    {
                        "symbol": symbol,
                        "open": float(bar.open),
                        "close": float(bar.close),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "volume": int(bar.volume),
                        "datetime": str(bar.date),
                    }
                )
            return candles
        except Exception as e:
            raise BrokerError(
                f"Failed to get historical prices from IBKR: {e}"
            ) from e

    def place_order(self, account: str, order: dict) -> dict:
        """Place an order with IBKR."""
        try:
            from ib_insync import LimitOrder, MarketOrder, Stock, StopOrder

            instruction = ""
            quantity = 0
            symbol = ""
            if "orderLegCollection" in order and order["orderLegCollection"]:
                leg = order["orderLegCollection"][0]
                instruction = leg.get("instruction", "BUY")
                quantity = leg.get("quantity", 0)
                symbol = leg.get("instrument", {}).get("symbol", "")

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            order_type = order.get("orderType", "MARKET")
            if order_type == "MARKET":
                ib_order = MarketOrder(instruction, quantity)
            elif order_type == "LIMIT":
                ib_order = LimitOrder(
                    instruction, quantity, order.get("price", 0.0)
                )
            elif order_type == "STOP":
                ib_order = StopOrder(
                    instruction, quantity, order.get("stopPrice", 0.0)
                )
            else:
                ib_order = MarketOrder(instruction, quantity)

            trade = self._ib.placeOrder(contract, ib_order)

            return {
                "order_id": str(trade.order.orderId),
                "status": str(trade.orderStatus.status),
                "request_body": order,
            }
        except Exception as e:
            raise OrderRejectedError(f"Order rejected by IBKR: {e}") from e

    def get_order_status(self, account: str, order_id: str) -> dict:
        """Get order status from IBKR.

        Checks open trades first, then all completed trades.
        Returns UNKNOWN (not FILLED) when order cannot be found,
        since 'not found' does not mean 'filled'.
        """
        try:
            for trade in self._ib.openTrades():
                if str(trade.order.orderId) == order_id:
                    return {
                        "order_id": order_id,
                        "status": str(trade.orderStatus.status),
                        "filled_quantity": trade.orderStatus.filled,
                        "remaining_quantity": trade.orderStatus.remaining,
                    }

            for trade in self._ib.allTrades():
                if str(trade.order.orderId) == order_id:
                    return {
                        "order_id": order_id,
                        "status": str(trade.orderStatus.status),
                        "filled_quantity": trade.orderStatus.filled,
                        "remaining_quantity": trade.orderStatus.remaining,
                    }

            logger.warning(
                f"Order {order_id} not found in open or completed trades. "
                f"Returning UNKNOWN status — requires reconciliation."
            )
            return {
                "order_id": order_id,
                "status": "UNKNOWN",
                "filled_quantity": 0,
                "remaining_quantity": 0,
            }
        except Exception as e:
            raise BrokerError(
                f"Failed to get order status from IBKR: {e}"
            ) from e

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order with IBKR.

        Looks the order up among open trades and cancels it via
        ib_insync's cancelOrder. Returns False if the order id is not
        an open order (already filled or unknown).
        """
        try:
            if self._ib is None:
                raise BrokerError("IBKR not connected; authenticate() first")
            for trade in self._ib.openTrades():
                if str(trade.order.orderId) == order_id:
                    self._ib.cancelOrder(trade.order)
                    logger.info(f"Cancelled IBKR order {order_id}")
                    return True

            logger.warning(
                f"Cancel failed for order {order_id}: not an open order"
            )
            return False
        except Exception as e:
            raise BrokerError(
                f"Failed to cancel order {order_id} at IBKR: {e}"
            ) from e

    def get_open_orders(self, account: Optional[str] = None) -> List[dict]:
        """Get open orders from IBKR."""
        try:
            if self._ib is None:
                raise BrokerError("IBKR not connected; authenticate() first")
            return [
                {
                    "order_id": str(trade.order.orderId),
                    "symbol": trade.contract.symbol,
                    "status": str(trade.orderStatus.status),
                    "quantity": trade.order.totalQuantity,
                }
                for trade in self._ib.openTrades()
            ]
        except Exception as e:
            raise BrokerError(f"Failed to get open orders from IBKR: {e}") from e

    def get_account_info(self, account: str = None) -> dict:
        """Get account information from IBKR."""
        try:
            account_values = self._ib.accountSummary()

            info = {
                "account_number": account or "",
                "cash_balance": 0.0,
                "buying_power": 0.0,
                "long_market_value": 0.0,
                "short_market_value": 0.0,
            }

            for av in account_values:
                if av.tag == "CashBalance" and av.currency == "BASE":
                    info["cash_balance"] = float(av.value)
                elif av.tag == "BuyingPower" and av.currency == "BASE":
                    info["buying_power"] = float(av.value)
                elif av.tag == "LongMarketValue" and av.currency == "BASE":
                    info["long_market_value"] = float(av.value)
                elif av.tag == "ShortMarketValue" and av.currency == "BASE":
                    info["short_market_value"] = float(av.value)

            return info
        except Exception as e:
            raise BrokerError(
                f"Failed to get account info from IBKR: {e}"
            ) from e

    def get_positions(self, account: str = None) -> List[dict]:
        """Get positions from IBKR."""
        try:
            positions = self._ib.positions()

            result = []
            for pos in positions:
                result.append(
                    {
                        "symbol": pos.contract.symbol,
                        "quantity": pos.position,
                        "average_price": pos.avgCost,
                        "market_value": 0.0,
                        "asset_type": "EQUITY",
                    }
                )
            return result
        except Exception as e:
            raise BrokerError(f"Failed to get positions from IBKR: {e}") from e

    def get_option_chain(self, symbol: str) -> dict:
        """Get option chain from IBKR."""
        try:
            from ib_insync import Stock

            contract = Stock(symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            chains = self._ib.reqSecDefOptParams(
                symbol, "", "STK", conId=contract.conId
            )

            result = {"symbol": symbol, "expirations": [], "strikes": []}
            for chain in chains:
                result["expirations"].extend(chain.expirations)
                result["strikes"].extend(chain.strikes)

            result["expirations"] = sorted(set(result["expirations"]))
            result["strikes"] = sorted(set(result["strikes"]))

            return result
        except Exception as e:
            raise BrokerError(
                f"Failed to get option chain from IBKR: {e}"
            ) from e
