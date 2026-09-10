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

# Asset-class labels for the metals universe (futures + ETF proxies).
METALS_SECTORS: Dict[str, str] = {
    "GC=F": "Precious Metals",
    "SI=F": "Precious Metals",
    "GLD": "Precious Metals",
    "SLV": "Precious Metals",
}

# Asset-class labels for the crypto universe.
CRYPTO_SECTORS: Dict[str, str] = {
    "BTC-USD": "Cryptocurrency",
    "ETH-USD": "Cryptocurrency",
}

# Per-market risk limits. Crypto trades at 2–5x equity volatility, so its
# per-position exposure is capped lower; metals futures also carry roll risk.
# max_position_size_pct  → single-symbol fraction of equity at entry
# max_sector_exposure_pct → fraction of equity in one asset class
MARKET_RISK_LIMITS: Dict[str, Dict[str, float]] = {
    "US": {"max_position_size_pct": 0.12, "max_sector_exposure_pct": 0.25},
    "metals": {"max_position_size_pct": 0.10, "max_sector_exposure_pct": 0.20},
    "crypto": {"max_position_size_pct": 0.05, "max_sector_exposure_pct": 0.10},
}

_UNKNOWN_SECTOR = "UNKNOWN"

_MULTI_MARKET_SECTOR_MAP: Dict[str, str] = {
    **US_EQUITY_GICS_SECTORS,
    **METALS_SECTORS,
    **CRYPTO_SECTORS,
}


def gics_sector(symbol: str) -> str:
    """Return the GICS sector for a symbol, or ``UNKNOWN`` when unclassified."""
    return US_EQUITY_GICS_SECTORS.get(str(symbol).upper(), _UNKNOWN_SECTOR)


def sector(symbol: str) -> str:
    """Return the market sector/asset class for a symbol across all markets."""
    return _MULTI_MARKET_SECTOR_MAP.get(str(symbol).upper(), _UNKNOWN_SECTOR)


def market_for_symbol(symbol: str) -> str:
    """Classify a symbol into its market (US | metals | crypto | unknown)."""
    s = str(symbol).upper()
    if s in METALS_SECTORS:
        return "metals"
    if s in CRYPTO_SECTORS:
        return "crypto"
    if s in US_EQUITY_GICS_SECTORS:
        return "US"
    return "unknown"


def risk_limits_for_symbols(symbols: Iterable[str]) -> Dict[str, float]:
    """Return the tightest per-position exposure limit for a universe."""
    markets = {market_for_symbol(s) for s in symbols}
    known = [MARKET_RISK_LIMITS[m]["max_position_size_pct"] for m in markets if m in MARKET_RISK_LIMITS]
    if not known:
        return {"max_position_size_pct": 0.10, "max_sector_exposure_pct": 0.20}
    return {
        "max_position_size_pct": min(known),
        "max_sector_exposure_pct": min(
            MARKET_RISK_LIMITS[m]["max_sector_exposure_pct"]
            for m in markets if m in MARKET_RISK_LIMITS
        ),
    }


def build_sector_map(symbols: Iterable[str]) -> Dict[str, str]:
    """Return a symbol → sector map covering the given universe (multi-market)."""
    return {symbol: sector(symbol) for symbol in symbols}
