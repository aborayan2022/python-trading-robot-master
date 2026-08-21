"""Market Data Feed abstraction with stale data detection and event publishing."""

import threading
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional
import pandas as pd

from pyrobot.data.base import Candle, MarketDataProvider, Quote
from pyrobot.exceptions import StaleDataError
from pyrobot.logging_config import get_logger

logger = get_logger("data_feed")


class MarketDataFeed:
    """Manages continuous market data streaming, replay, and stale feed protection.

    Attributes:
        provider: The underlying :class:`MarketDataProvider`.
        stale_threshold_seconds: Maximum allowed time without fresh quote/bar before raising StaleDataError.
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        stale_threshold_seconds: float = 60.0,
    ) -> None:
        self.provider = provider
        self.stale_threshold = timedelta(seconds=stale_threshold_seconds)
        self._last_heartbeat: Dict[str, datetime] = {}
        self._subscribers: List[Callable[[str, Quote], None]] = []
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[str, Quote], None]) -> None:
        """Register a subscriber callback for real-time quote updates."""
        with self._lock:
            self._subscribers.append(callback)

    def update_quote(self, symbol: str, quote: Quote) -> None:
        """Process an incoming quote and update feed freshness heartbeat."""
        with self._lock:
            self._last_heartbeat[symbol] = quote.timestamp
            for sub in self._subscribers:
                try:
                    sub(symbol, quote)
                except Exception as e:
                    logger.error("Subscriber error on symbol %s: %s", symbol, e)

    def check_staleness(self, symbol: str, current_time: Optional[datetime] = None) -> None:
        """Verify that data for the given symbol is not stale.

        Raises:
            StaleDataError: If the elapsed time since the last quote exceeds stale_threshold.
        """
        with self._lock:
            last = self._last_heartbeat.get(symbol)
            if last is None:
                return  # No data received yet

            now = current_time or datetime.now(timezone.utc)
            if (now - last) > self.stale_threshold:
                elapsed = (now - last).total_seconds()
                msg = f"Data feed for {symbol} is stale ({elapsed:.1f}s > {self.stale_threshold.total_seconds()}s)"
                logger.critical(msg)
                raise StaleDataError(msg)

    def get_latest_quote(self, symbol: str) -> Quote:
        """Fetch quote from provider and update heartbeat."""
        quote = self.provider.get_latest_quote(symbol)
        self.update_quote(symbol, quote)
        return quote
