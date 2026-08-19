"""Data Platform domain models and abstract provider interfaces.

Defines:
    - DataFrequency (TICK, MINUTE, HOUR, DAILY)
    - Candle (OHLCV representation with UTC timezone awareness)
    - Quote (Bid/Ask/Last snapshot)
    - MarketDataProvider (Abstract base class for all market data sources)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
import pandas as pd


class DataFrequency(str, Enum):
    """Supported bar aggregation frequencies."""

    TICK = "tick"
    SECOND_1 = "1s"
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    DAILY = "1d"
    WEEKLY = "1w"


@dataclass(frozen=True)
class Candle:
    """Immutable single price candle (OHLCV).

    Attributes:
        symbol: Ticker symbol (e.g. 'AAPL').
        timestamp: Time of the candle in UTC.
        open: Open price (> 0).
        high: Highest price (>= open, close, low).
        low: Lowest price (<= open, close, high).
        close: Close price (> 0).
        volume: Traded volume (>= 0).
        vwap: Optional volume-weighted average price.
    """

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "datetime": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "vwap": self.vwap,
        }


@dataclass(frozen=True)
class Quote:
    """Top of book snapshot."""

    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    last_price: float
    bid_size: float = 0.0
    ask_size: float = 0.0

    @property
    def spread(self) -> float:
        return max(0.0, self.ask - self.bid)

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2.0 if (self.bid > 0 and self.ask > 0) else self.last_price


class MarketDataProvider(ABC):
    """Abstract interface for all Market Data Providers.

    Separates market data acquisition completely from broker order placement.
    """

    @abstractmethod
    def get_historical_candles(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: DataFrequency = DataFrequency.MINUTE_1,
    ) -> List[Candle]:
        """Fetch historical candles between start and end (inclusive)."""
        ...

    @abstractmethod
    def get_latest_quote(self, symbol: str) -> Quote:
        """Fetch the most recent top-of-book quote."""
        ...

    @abstractmethod
    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Batch fetch latest quotes for multiple symbols."""
        ...

    def to_dataframe(self, candles: List[Candle]) -> pd.DataFrame:
        """Convert a list of Candles to a standard indexed Pandas DataFrame."""
        if not candles:
            return pd.DataFrame(
                columns=["symbol", "open", "high", "low", "close", "volume", "vwap"]
            )

        data = [c.to_dict() for c in candles]
        df = pd.DataFrame(data)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df.set_index("datetime", inplace=True)
        df.sort_index(inplace=True)
        return df
