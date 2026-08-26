"""Alpaca broker adapter for commission-free trading."""

import os
from datetime import datetime
from typing import Dict, List, Optional

from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import AuthenticationError, BrokerError, OrderRejectedError
from pyrobot.logging_config import get_logger

logger = get_logger("alpaca")


class AlpacaBroker(BrokerInterface):
    """Alpaca broker adapter for commission-free US equities/ETFs.

    Requires:
        pip install python-trading-robot[alpaca]

    Supports both live and paper trading via Alpaca's API.
    """

    def __init__(
        self,
        api_key: str = None,
        secret_key: str = None,
        base_url: str = None,
        paper: bool = True,
        **kwargs,
    ) -> None:
        self._api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self._secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        self._paper = paper

        if base_url:
            self._base_url = base_url
        elif paper:
            self._base_url = "https://paper-api.alpaca.markets"
        else:
            self._base_url = "https://api.alpaca.markets"

        self._trading_client = None
        self._data_client = None

    @property
    def name(self) -> str:
        return "alpaca"

    def authenticate(self) -> bool:
        """Authenticate with Alpaca."""
        try:
            from alpaca.trading.client import TradingClient

            self._trading_client = TradingClient(
                api_key=self._api_key,
                secret_key=self._secret_key,
                paper=self._paper,
            )

            account = self._trading_client.get_account()
            logger.info(
                f"Authenticated with Alpaca (paper={self._paper}). "
                f"Account status: {account.status}"
            )
            return True
        except Exception as e:
            raise AuthenticationError(f"Alpaca authentication failed: {e}") from e

    def get_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        """Get current quotes from Alpaca."""
        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            self._ensure_data_client()

            request = StockLatestQuoteRequest(symbol_or_symbols=symbols)
            quotes = self._data_client.get_stock_latest_quote(request)

            normalized = {}
            for symbol, quote in quotes.items():
                normalized[symbol] = {
                    "symbol": symbol,
                    "last_price": float(quote.ask_price + quote.bid_price) / 2,
                    "bid": float(quote.bid_price),
                    "ask": float(quote.ask_price),
                    "open": 0.0,
                    "high": 0.0,
                    "low": 0.0,
                    "volume": 0,
                }
            return normalized
        except Exception as e:
            raise BrokerError(f"Failed to get quotes from Alpaca: {e}") from e

    def _ensure_data_client(self):
        """Lazily initialize the Alpaca data client."""
        if self._data_client is None:
            from alpaca.data import StockHistoricalDataClient

            self._data_client = StockHistoricalDataClient(
                api_key=self._api_key,
                secret_key=self._secret_key,
            )

    def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        bar_size: int = 1,
        bar_type: str = "minute",
    ) -> List[dict]:
        """Get historical prices from Alpaca."""
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            self._ensure_data_client()

            timeframe_map = {
                "minute": TimeFrame.Minute,
                "hour": TimeFrame.Hour,
                "day": TimeFrame.Day,
            }

            timeframe = timeframe_map.get(bar_type, TimeFrame.Minute)
            if bar_size != 1:
                timeframe = TimeFrame(bar_size, bar_type)

            request = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=timeframe,
                start=start,
                end=end,
            )
            bars = self._data_client.get_stock_bars(request)

            candles = []
            for bar in bars[symbol]:
                candles.append(
                    {
                        "symbol": symbol,
                        "open": float(bar.open),
                        "close": float(bar.close),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "volume": int(bar.volume),
                        "datetime": bar.timestamp.isoformat(),
                    }
                )
            return candles
        except Exception as e:
            raise BrokerError(
                f"Failed to get historical prices from Alpaca: {e}"
            ) from e

    def place_order(self, account: str, order: dict) -> dict:
        """Place an order with Alpaca.

        Extracts symbol from orderLegCollection[0].instrument.symbol
        (canonical order model) with fallback to top-level 'symbol' key.
        """
        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest

            if self._trading_client is None:
                self.authenticate()

            side_map = {
                "BUY": OrderSide.BUY,
                "SELL": OrderSide.SELL,
                "SELL_SHORT": OrderSide.SELL,
                "BUY_TO_COVER": OrderSide.BUY,
            }

            instruction = ""
            quantity = 0
            symbol = ""
            if "orderLegCollection" in order and order["orderLegCollection"]:
                leg = order["orderLegCollection"][0]
                instruction = leg.get("instruction", "BUY")
                quantity = leg.get("quantity", 0)
                instrument = leg.get("instrument", {})
                symbol = instrument.get("symbol", "")

            if not symbol:
                symbol = order.get("symbol", "")

            if not symbol:
                raise OrderRejectedError(
                    "Order rejected: no symbol found in order structure. "
                    "Expected orderLegCollection[0].instrument.symbol or top-level 'symbol'."
                )

            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=quantity,
                side=side_map.get(instruction, OrderSide.BUY),
                time_in_force=TimeInForce.DAY,
            )

            submitted = self._trading_client.submit_order(order_request)

            return {
                "order_id": str(submitted.id),
                "status": str(submitted.status.value),
                "request_body": order,
            }
        except Exception as e:
            raise OrderRejectedError(f"Order rejected by Alpaca: {e}") from e

    def get_order_status(self, account: str, order_id: str) -> dict:
        """Get order status from Alpaca."""
        try:
            if self._trading_client is None:
                self.authenticate()

            order = self._trading_client.get_order_by_id(order_id)

            return {
                "order_id": order_id,
                "status": str(order.status.value),
                "quantity": float(order.qty or 0),
                "filled_quantity": float(order.filled_qty or 0),
                "remaining_quantity": float(order.qty or 0)
                - float(order.filled_qty or 0),
                "avg_fill_price": float(order.filled_avg_price or 0),
            }
        except Exception as e:
            raise BrokerError(f"Failed to get order status from Alpaca: {e}") from e

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order with Alpaca.

        Returns True if the cancel request was accepted.
        """
        try:
            if self._trading_client is None:
                self.authenticate()
            self._trading_client.cancel_order(order_id=order_id)
            logger.info(f"Cancelled Alpaca order {order_id}")
            return True
        except Exception as e:
            raise BrokerError(f"Failed to cancel order {order_id} at Alpaca: {e}") from e

    def get_open_orders(self, account: Optional[str] = None) -> List[dict]:
        """Get open orders from Alpaca."""
        try:
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest

            if self._trading_client is None:
                self.authenticate()
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self._trading_client.get_orders(request)

            return [
                {
                    "order_id": str(order.id),
                    "symbol": order.symbol,
                    "status": str(order.status.value),
                    "quantity": float(order.qty or 0),
                }
                for order in orders
            ]
        except Exception as e:
            raise BrokerError(f"Failed to get open orders from Alpaca: {e}") from e

    def get_account_info(self, account: str = None) -> dict:
        """Get account information from Alpaca."""
        try:
            if self._trading_client is None:
                self.authenticate()
            acc = self._trading_client.get_account()

            return {
                "account_number": str(acc.id),
                "cash_balance": float(acc.cash),
                "buying_power": float(acc.buying_power),
                "long_market_value": float(acc.long_market_value),
                "short_market_value": float(acc.short_market_value),
            }
        except Exception as e:
            raise BrokerError(f"Failed to get account info from Alpaca: {e}") from e

    def get_positions(self, account: str = None) -> List[dict]:
        """Get positions from Alpaca."""
        try:
            if self._trading_client is None:
                self.authenticate()
            positions = self._trading_client.get_all_positions()

            result = []
            for pos in positions:
                result.append(
                    {
                        "symbol": pos.symbol,
                        "quantity": float(pos.qty),
                        "average_price": float(pos.avg_entry_price),
                        "market_value": float(pos.market_value),
                        "asset_type": "EQUITY",
                    }
                )
            return result
        except Exception as e:
            raise BrokerError(f"Failed to get positions from Alpaca: {e}") from e

    def get_option_chain(self, symbol: str) -> dict:
        """Get option chain from Alpaca."""
        try:
            from alpaca.data.requests import OptionChainRequest

            self._ensure_data_client()

            request = OptionChainRequest(underlying_symbol=symbol)
            chain = self._data_client.get_option_chain(request)

            return {"symbol": symbol, "chain": chain}
        except Exception as e:
            raise BrokerError(
                f"Failed to get option chain from Alpaca: {e}"
            ) from e
