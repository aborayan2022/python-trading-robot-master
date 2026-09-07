"""GICS sector classifications for the US equity trading universe.

Fixed GICS (Global Industry Classification Standard) sector labels for the
paper-trading universe. Without these, ``ExposureMonitor`` buckets every
position under the single ``UNKNOWN`` sector, so the conservative 15%
sector-concentration limit caps *all* concurrent entries regardless of how
diversified the universe actually is. With the map wired in, each real
sector gets its own concentration headroom.

Unknown symbols fall back to ``UNKNOWN`` (the conservative default), so the
limit still applies defensively to any symbol not in the curated map.
"""

from __future__ import annotations

from typing import Dict, Iterable

US_EQUITY_GICS_SECTORS: Dict[str, str] = {
    "AAPL": "Information Technology",
    "AMZN": "Consumer Discretionary",
    "GOOGL": "Communication Services",
    "JNJ": "Health Care",
    "JPM": "Financials",
    "META": "Communication Services",
    "MSFT": "Information Technology",
    "NVDA": "Information Technology",
    "WMT": "Consumer Staples",
    "XOM": "Energy",
}

_UNKNOWN_SECTOR = "UNKNOWN"


def gics_sector(symbol: str) -> str:
    """Return the GICS sector for a symbol, or ``UNKNOWN`` when unclassified."""
    return US_EQUITY_GICS_SECTORS.get(str(symbol).upper(), _UNKNOWN_SECTOR)


def build_sector_map(symbols: Iterable[str]) -> Dict[str, str]:
    """Return a symbol → GICS-sector map covering the given universe."""
    return {symbol: gics_sector(symbol) for symbol in symbols}
