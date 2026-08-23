"""Schwab broker adapter wrapping schwab-py."""

import os
from datetime import datetime
from typing import Dict, List, Optional

from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import AuthenticationError, BrokerError, OrderRejectedError
from pyrobot.logging_config import get_logger

logger = get_logger("schwab")


class SchwabBroker(BrokerInterface):
    """Schwab broker adapter using the schwab-py library.

    Requires:
        pip install python-trading-robot[schwab]
        Python >= 3.10

    Authentication is done via OAuth 2.0 through the Schwab Developer Portal.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "https://127.0.0.1:8182/callback",
        token_path: str = None,
        **kwargs,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token_path = token_path or os.path.join(
            os.path.expanduser("~"), ".schwab", "token.json"
        )
        self._client = None
        self._last_account: Optional[str] = None

    @property
    def name(self) -> str:
        return "schwab"

    def authenticate(self) -> bool:
        """Authenticate with Schwab using schwab-py."""
        try:
            from schwab import auth

            self._client = auth.Client(
                api_key=self._client_id,
                app_secret=self._client_secret,
                redirect_uri=self._redirect_uri,
                token_file=self._token_path,
            )
            logger.info("Successfully authenticated with Schwab")
            return True
        except Exception as e:
            raise AuthenticationError(f"Schwab authentication failed: {e}") from e

    def _normalize_candle(self, symbol: str, candle: dict) -> dict:
        """Normalize a Schwab candle to our standard format."""
        return {
            "symbol": symbol,
            "open": candle.get("open", 0.0),
            "close": candle.get("close", 0.0),
            "high": candle.get("high", 0.0),
            "low": candle.get("low", 0.0),
            "volume": int(candle.get("volume", 0)),
            "datetime": candle.get("datetime", ""),
        }

    def get_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        """Get current quotes from Schwab."""
        try:
            response = self._client.get_quotes(symbols=symbols)
            response.raise_for_status()
            raw_quotes = response.json()

            normalized = {}
            for symbol, data in raw_quotes.items():
                quote_data = data.get("quote", data)
                normalized[symbol] = {
                    "symbol": symbol,
                    "last_price": quote_data.get("lastPrice", 0.0),
                    "bid": quote_data.get("bidPrice", 0.0),
                    "ask": quote_data.get("askPrice", 0.0),
                    "open": quote_data.get("openPrice", 0.0),
                    "high": quote_data.get("highPrice", 0.0),
                    "low": quote_data.get("lowPrice", 0.0),
                    "volume": int(quote_data.get("totalVolume", 0)),
                }
            return normalized
        except Exception as e:
            raise BrokerError(f"Failed to get quotes from Schwab: {e}") from e

    def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        bar_size: int = 1,
        bar_type: str = "minute",
    ) -> List[dict]:
        """Get historical prices from Schwab."""
        try:
            frequency_map = {
                "minute": self._client.PriceHistory.Frequency.FREQUENCY_MINUTE,
                "daily": self._client.PriceHistory.Frequency.FREQUENCY_DAILY,
                "weekly": self._client.PriceHistory.Frequency.FREQUENCY_WEEKLY,
            }

            response = self._client.get_price_history(
                symbol=symbol,
                period_type=self._client.PriceHistory.PeriodType.DAY,
                start_datetime=start,
                end_datetime=end,
                frequency_type=frequency_map.get(
                    bar_type,
                    self._client.PriceHistory.FrequencyType.FREQUENCY_TYPE_MINUTE,
                ),
                frequency=bar_size,
                need_extended_hours_data=True,
            )
            response.raise_for_status()
            data = response.json()

            candles = []
            for candle in data.get("candles", []):
                candles.append(
                    self._normalize_candle(
                        symbol=symbol,
                        candle={
                            "open": candle["open"],
                            "close": candle["close"],
                            "high": candle["high"],
                            "low": candle["low"],
                            "volume": candle["volume"],
                            "datetime": candle["datetime"],
                        },
                    )
                )
            return candles
        except Exception as e:
            raise BrokerError(
                f"Failed to get historical prices from Schwab: {e}"
            ) from e

    def place_order(self, account: str, order: dict) -> dict:
        """Place an order with Schwab."""
        try:
            response = self._client.place_order(account_number=account, order=order)
            response.raise_for_status()

            self._last_account = account
            order_id = response.headers.get("Location", "").split("/")[-1]

            return {
                "order_id": order_id,
                "status": "QUEUED",
                "request_body": order,
            }
        except Exception as e:
            raise OrderRejectedError(f"Order rejected by Schwab: {e}") from e

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order with Schwab.

        Uses the account number from the most recent place_order call
        (the Schwab order API is account-scoped).
        """
        try:
            if self._client is None:
                raise BrokerError(
                    "Schwab client not initialized; authenticate() first"
                )
            account = self._last_account
            if not account:
                logger.warning(
                    f"Cannot cancel order {order_id}: no account number known. "
                    "Place an order first or pass the account explicitly."
                )
                return False

            response = self._client.cancel_order(
                order_id=order_id, account_number=account
            )
            response.raise_for_status()
            logger.info(f"Cancelled Schwab order {order_id}")
            return True
        except Exception as e:
            raise BrokerError(
                f"Failed to cancel order {order_id} at Schwab: {e}"
            ) from e

    def get_order_status(self, account: str, order_id: str) -> dict:
        """Get order status from Schwab."""
        try:
            response = self._client.get_order(order_id=order_id, account_number=account)
            response.raise_for_status()
            data = response.json()

            return {
                "order_id": order_id,
                "status": data.get("status", "UNKNOWN"),
                "filled_quantity": data.get("quantity", 0),
                "remaining_quantity": data.get("remainingQuantity", 0),
            }
        except Exception as e:
            raise BrokerError(f"Failed to get order status from Schwab: {e}") from e

    def get_account_info(self, account: str = None) -> dict:
        """Get account information from Schwab."""
        try:
            response = self._client.get_account(account_number=account)
            response.raise_for_status()
            data = response.json()

            balances = data.get("securitiesAccount", {}).get("currentBalances", {})

            return {
                "account_number": data.get("securitiesAccount", {}).get(
                    "accountId", account
                ),
                "cash_balance": balances.get("cashBalance", 0.0),
                "buying_power": balances.get("buyingPower", 0.0),
                "long_market_value": balances.get("longMarketValue", 0.0),
                "short_market_value": balances.get("shortMarketValue", 0.0),
            }
        except Exception as e:
            raise BrokerError(f"Failed to get account info from Schwab: {e}") from e

    def get_positions(self, account: str = None) -> List[dict]:
        """Get positions from Schwab."""
        try:
            response = self._client.get_account(
                account_number=account, fields=["positions"]
            )
            response.raise_for_status()
            data = response.json()

            positions = []
            for pos in data.get("securitiesAccount", {}).get("positions", []):
                instrument = pos.get("instrument", {})
                positions.append(
                    {
                        "symbol": instrument.get("symbol", ""),
                        "quantity": pos.get("longQuantity", 0)
                        - pos.get("shortQuantity", 0),
                        "average_price": pos.get("averagePrice", 0.0),
                        "market_value": pos.get("marketValue", 0.0),
                        "asset_type": instrument.get("assetType", ""),
                    }
                )
            return positions
        except Exception as e:
            raise BrokerError(f"Failed to get positions from Schwab: {e}") from e

    def get_option_chain(self, symbol: str) -> dict:
        """Get option chain from Schwab."""
        try:
            response = self._client.get_option_chain(symbol=symbol)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise BrokerError(
                f"Failed to get option chain from Schwab: {e}"
            ) from e
