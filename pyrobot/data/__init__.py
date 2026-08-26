"""Data platform foundations — providers, quality, storage, and streaming feeds."""

from pyrobot.data.base import Candle, DataFrequency, MarketDataProvider, Quote
from pyrobot.data.feed import MarketDataFeed
from pyrobot.data.quality import DataAnomaly, DataQualityEngine, DataQualityReport, DatasetMetadata
from pyrobot.data.storage import DatasetStore, DatasetVersion

try:
    from pyrobot.data.alpaca import AlpacaDataProvider, is_us_equity_session
except Exception:  # pragma: no cover - alpaca-py is optional
    AlpacaDataProvider = None  # type: ignore[misc, assignment]
    is_us_equity_session = None  # type: ignore[misc, assignment]

__all__ = [
    "MarketDataProvider",
    "Candle",
    "Quote",
    "DataFrequency",
    "DataQualityEngine",
    "DataQualityReport",
    "DataAnomaly",
    "DatasetMetadata",
    "DatasetStore",
    "DatasetVersion",
    "MarketDataFeed",
    "AlpacaDataProvider",
    "is_us_equity_session",
]
