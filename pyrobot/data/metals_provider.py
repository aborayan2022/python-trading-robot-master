"""Precious Metals data provider via yfinance.

Downloads and caches daily OHLCV for gold, silver, platinum, and palladium
using Yahoo Finance futures tickers (GC=F, SI=F) and ETF tickers (GLD, SLV).
Data is cached in ``data/metals/`` for offline backtesting.

Environment:
    PYROBOT_DATA_DIR  root for data/ (default ".")
    PYROBOT_METALS_YEARS  years of history (default 5)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from pyrobot.data.base import Candle, DataFrequency, MarketDataProvider, Quote
from pyrobot.logging_config import get_logger

logger = get_logger("metals_provider")

ROOT = Path(os.environ.get("PYROBOT_DATA_DIR", ".")).resolve()
DATA_DIR = ROOT / "data" / "metals"

# Default metals universe — futures + ETFs for redundancy.
DEFAULT_METALS = ["GC=F", "SI=F", "GLD", "SLV"]

# Trading calendar: COMEX Globex hours (nearly 24h, closed weekends).
# For daily bars this matters less, but we document it for intraday future use.
TRADING_CALENDAR = {
    "name": "COMEX_Globex",
    "hours": "Sun 18:00 – Fri 17:00 ET (23h/day)",
    "closed": "Sat all day, Sun before 18:00 ET",
    "timezone": "America/New_York",
}


class MetalsProvider(MarketDataProvider):
    """yfinance-based provider for precious metals data.

    Caches downloaded data as CSV in ``data/metals/`` for reproducible
    backtesting without network access.
    """

    TRADING_CALENDAR = TRADING_CALENDAR

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        years: int = int(os.environ.get("PYROBOT_METALS_YEARS", "5")),
        data_dir: Optional[Path] = None,
    ) -> None:
        self._symbols = list(symbols or DEFAULT_METALS)
        self._years = years
        self._data_dir = data_dir or DATA_DIR
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, pd.DataFrame] = {}

    # ── MarketDataProvider interface ───────────────────────────────────────────

    def get_historical_candles(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        frequency: DataFrequency = DataFrequency.DAILY,
    ) -> List[Candle]:
        df = self._load_or_download(symbol)
        if df is None or df.empty:
            return []

        mask = (df.index >= pd.Timestamp(start)) & (
            df.index <= pd.Timestamp(end)
        )
        sliced = df.loc[mask]

        candles: List[Candle] = []
        for ts, row in sliced.iterrows():
            candles.append(
                Candle(
                    symbol=symbol,
                    timestamp=ts.to_pydatetime(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return candles

    def get_latest_quote(self, symbol: str) -> Quote:
        df = self._load_or_download(symbol)
        if df is None or df.empty:
            raise ValueError(f"No data for {symbol}")
        last = df.iloc[-1]
        close = float(last["close"])
        return Quote(
            symbol=symbol,
            timestamp=df.index[-1].to_pydatetime(),
            bid=close,
            ask=close,
            last_price=close,
        )

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        return {s: self.get_latest_quote(s) for s in symbols}

    # ── Data acquisition ──────────────────────────────────────────────────────

    def _load_or_download(self, symbol: str, refresh: bool = False) -> Optional[pd.DataFrame]:
        if symbol in self._cache and not refresh:
            return self._cache[symbol]

        cache_path = self._data_dir / f"{symbol.replace('=', '_')}.csv"
        if cache_path.exists() and not refresh:
            df = pd.read_csv(cache_path, parse_dates=["datetime"], index_col="datetime")
            df = df.tz_localize("UTC") if df.index.tz is None else df
            self._cache[symbol] = df
            logger.info(
                "Loaded %s from cache: %d rows (%s → %s)",
                symbol, len(df), df.index[0].date(), df.index[-1].date(),
            )
            return df

        df = self._download(symbol)
        if df is not None and not df.empty:
            df.to_csv(cache_path)
            self._cache[symbol] = df
            logger.info(
                "Downloaded %s: %d rows (%s → %s), cached to %s",
                symbol, len(df), df.index[0].date(), df.index[-1].date(), cache_path,
            )
        return df

    def _download(self, symbol: str) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf

            raw = yf.Ticker(symbol).history(
                period=f"{self._years}y", interval="1d", auto_adjust=True
            )
            if raw.empty:
                logger.warning("yfinance returned empty data for %s", symbol)
                return None

            df = pd.DataFrame(
                {
                    "open": raw["Open"].astype(float),
                    "high": raw["High"].astype(float),
                    "low": raw["Low"].astype(float),
                    "close": raw["Close"].astype(float),
                    "volume": raw["Volume"].astype(float),
                }
            )
            df.index = pd.to_datetime(df.index, utc=True)
            df.index.name = "datetime"
            df["symbol"] = symbol
            return df

        except ImportError:
            logger.error("yfinance is required for MetalsProvider: pip install yfinance")
            return None
        except Exception as exc:
            logger.error("Failed to download %s: %s", symbol, exc)
            return None

    def download_all(self, refresh: bool = False) -> Dict[str, pd.DataFrame]:
        """Download/cache all default metals symbols. Returns symbol → DataFrame."""
        frames: Dict[str, pd.DataFrame] = {}
        for symbol in self._symbols:
            if refresh:
                self._cache.pop(symbol, None)
            df = self._load_or_download(symbol, refresh=refresh)
            if df is not None and not df.empty:
                frames[symbol] = df
        return frames

    def load_cached(self) -> Dict[str, pd.DataFrame]:
        """Load all cached metals data without downloading."""
        frames: Dict[str, pd.DataFrame] = {}
        for symbol in self._symbols:
            df = self._load_or_download(symbol)
            if df is not None and not df.empty:
                frames[symbol] = df
        return frames
