"""Abstract base class for all broker adapters."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional


class BrokerInterface(ABC):
    """Abstract base class that all broker adapters must implement.

    Each broker adapter normalizes its API responses to a common dict format:
        {
            'symbol': str,
            'open': float,
            'close': float,
            'high': float,
            'low': float,
            'volume': int,
            'datetime': str (ISO format)
        }
    """

    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the broker. Returns True on success."""
        ...

    @abstractmethod
    def get_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        """Get current quotes for a list of symbols.

        Returns a dict keyed by symbol, each value containing at minimum:
            {'symbol', 'last_price', 'bid', 'ask', 'open', 'high', 'low', 'volume'}
        """
        ...

    @abstractmethod
    def get_historical_prices(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        bar_size: int = 1,
        bar_type: str = "minute",
    ) -> List[dict]:
        """Get historical price candles for a symbol.

        Returns a list of normalized dicts:
            {'symbol', 'open', 'close', 'high', 'low', 'volume', 'datetime'}
        """
        ...

    @abstractmethod
    def place_order(self, account: str, order: dict) -> dict:
        """Submit an order to the broker.

        Returns an order response dict with at minimum:
            {'order_id', 'status', 'request_body'}
        """
        ...

    @abstractmethod
    def get_order_status(self, account: str, order_id: str) -> dict:
        """Get the status of an order.

        Returns a dict with at minimum:
            {'order_id', 'status', 'quantity', 'filled_quantity',
             'remaining_quantity', 'avg_fill_price'}
        """
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order.

        Arguments:
        ----
        order_id {str} -- The broker-assigned order id to cancel.

        Returns:
        ----
        {bool} -- True if the order was cancelled, False if it could
            not be cancelled (unknown, already filled, or otherwise
            in a terminal state).
        """
        ...

    def get_open_orders(self, account: Optional[str] = None) -> List[dict]:
        """Get currently open (working) orders for an account.

        Returns a list of dicts, each with at minimum:
            {'order_id', 'status', 'quantity'}

        The default implementation returns an empty list. Adapters
        with a cheap open-orders endpoint should override this.
        """
        return []

    @abstractmethod
    def get_account_info(self, account: str = None) -> dict:
        """Get account information.

        Returns a dict with at minimum:
            {'account_number', 'cash_balance', 'buying_power', 'long_market_value'}
        """
        ...

    @abstractmethod
    def get_positions(self, account: str = None) -> List[dict]:
        """Get all positions for an account.

        Returns a list of dicts, each with at minimum:
            {'symbol', 'quantity', 'average_price', 'market_value'}
        """
        ...

    @abstractmethod
    def get_option_chain(self, symbol: str) -> dict:
        """Get the option chain for a symbol.

        Returns a dict with option expiration dates and strike prices.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the broker name identifier."""
        ...
