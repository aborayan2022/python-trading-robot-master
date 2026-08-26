"""Alpaca market-data provider for US equities.

The provider is intentionally read-only: order placement stays in
``pyrobot.brokers.alpaca_broker`` while this module owns historical bars,
latest quotes, polling bars, UTC normalization, and basic market-session
guards used by the production paper profile.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from pyrobot.data.base import Candle, DataFrequency, MarketDataProvider, Quote
from pyrobot.exceptions import BrokerError, StaleDataError

_EASTERN = ZoneInfo("America/New_York")


def _utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_us_equity_session(ts: Optional[datetime] = None) -> bool:
    """Conservative regular-session check for US equities.

    This covers weekdays 09:30-16:00 America/New_York. Exchange holidays are
    not embedded here because Alpaca remains the source of truth for returned
    bars; a missing bar during a requested poll is handled as stale data.
    """
    local = _utc(ts or datetime.now(timezone.utc)).astimezone(_EASTERN)
    if local.weekday() >= 5:
        return False
    return time(9, 30) <= local.time() <= time(16, 0)


def _timeframe(frequency: DataFrequency):
    from alpaca.data.timeframe import TimeFrame  # type: ignore[import-not-found]

    mapping = {
        DataFrequency.MINUTE_1: TimeFrame.Minute,
        DataFrequency.HOUR_1: TimeFrame.Hour,
        DataFrequency.DAILY: TimeFrame.Day,
    }
    if frequency not in mapping:
        raise ValueError(f"Unsupported Alpaca frequency: {frequency.value}")
    return mapping[frequency]


def _data_feed(feed: Optional[str]) -> Any:
    if not feed:
        return None
    try:
        from alpaca.data.enums import DataFeed  # type: ignore[import-not-found]

        return DataFeed(feed)
    except Exception:
        return feed


@dataclass
class AlpacaDataProvider(MarketDataProvider):
    """Read-only Alpaca StockHistoricalDataClient adapter."""

    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    feed: Optional[str] = None

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("ALPACA_API_KEY", "")
        self.secret_key = self.secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        self.feed = self.feed or os.environ.get("ALPACA_DATA_FEED", "iex")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from alpaca.data import StockHistoricalDataClient  # type: ignore[import-not-found]

            self._client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
        return self._client

    def get_historical_candles(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: DataFrequency = DataFrequency.MINUTE_1,
    ) -> List[Candle]:
        """Fetch normalized historical OHLCV candles for one symbol."""
        try:
            request: Any
            try:
                from alpaca.data.requests import StockBarsRequest  # type: ignore[import-not-found]
            except ImportError:
                if self._client is None:
                    raise
                request = None
            else:
                request = StockBarsRequest(
                    symbol_or_symbols=[symbol.upper()],
                    timeframe=_timeframe(frequency),
                    start=_utc(start),
                    end=_utc(end),
                    feed=_data_feed(self.feed),
                )
            bars = self._ensure_client().get_stock_bars(request)
            raw_bars = _lookup_symbol_payload(bars, symbol.upper())
            candles = [
                Candle(
                    symbol=symbol.upper(),
                    timestamp=_utc(bar.timestamp),
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=float(bar.volume),
                    vwap=float(bar.vwap) if getattr(bar, "vwap", None) is not None else None,
                )
                for bar in raw_bars
            ]
            candles.sort(key=lambda c: c.timestamp)
            return candles
        except Exception as exc:
            raise BrokerError(f"Failed to fetch Alpaca historical bars for {symbol}: {exc}") from exc

    def get_latest_quote(self, symbol: str) -> Quote:
        """Fetch the latest top-of-book quote for one symbol."""
        return self.get_quotes([symbol])[symbol.upper()]

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """Fetch latest quotes for multiple symbols."""
        try:
            clean_symbols = [s.upper() for s in symbols]
            request: Any
            try:
                from alpaca.data.requests import (
                    StockLatestQuoteRequest,  # type: ignore[import-not-found]
                )
            except ImportError:
                if self._client is None:
                    raise
                request = None
            else:
                request = StockLatestQuoteRequest(
                    symbol_or_symbols=clean_symbols,
                    feed=_data_feed(self.feed),
                )

            quotes = self._ensure_client().get_stock_latest_quote(request)
            out: Dict[str, Quote] = {}
            for symbol in clean_symbols:
                quote = _lookup_symbol_payload(quotes, symbol)
                out[symbol] = Quote(
                    symbol=symbol,
                    timestamp=_utc(quote.timestamp),
                    bid=float(quote.bid_price),
                    ask=float(quote.ask_price),
                    last_price=float((quote.bid_price + quote.ask_price) / 2.0),
                    bid_size=float(getattr(quote, "bid_size", 0.0) or 0.0),
                    ask_size=float(getattr(quote, "ask_size", 0.0) or 0.0),
                )
            return out
        except Exception as exc:
            raise BrokerError(f"Failed to fetch Alpaca latest quotes: {exc}") from exc

    def poll_latest_bars(
        self,
        symbols: Iterable[str],
        *,
        lookback_minutes: int = 5,
        now: Optional[datetime] = None,
        require_market_session: bool = True,
    ) -> Dict[str, dict]:
        """Return one latest bar per symbol in TradingLoop bar-provider shape."""
        ts = _utc(now or datetime.now(timezone.utc))
        if require_market_session and not is_us_equity_session(ts):
            raise StaleDataError("US equity market is outside regular session")

        from datetime import timedelta

        result: Dict[str, dict] = {}
        for symbol in [s.upper() for s in symbols]:
            candles = self.get_historical_candles(
                symbol=symbol,
                start=ts - timedelta(minutes=lookback_minutes),
                end=ts,
                frequency=DataFrequency.MINUTE_1,
            )
            if not candles:
                raise StaleDataError(f"No recent Alpaca bar returned for {symbol}")
            candle = candles[-1]
            result[symbol] = {
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "datetime": candle.timestamp,
            }
        return result


def _lookup_symbol_payload(payload, symbol: str):
    """Handle dict-like and Alpaca BarSet/QuoteSet payloads in one place."""
    if isinstance(payload, dict):
        value = payload[symbol]
    else:
        value = payload[symbol]
    return value
