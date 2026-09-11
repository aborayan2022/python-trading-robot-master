"""DataProvider registry — maps market names to data providers.

Provides a central registry for data providers so that backtest scripts,
paper trading sessions, and training pipelines can instantiate the correct
provider based on a market name or environment variable.

Usage::

    from pyrobot.data.registry import DataProviderRegistry

    # Register providers (typically done at import time).
    DataProviderRegistry.register("us", AlpacaDataProvider)
    DataProviderRegistry.register("metals", MetalsProvider)
    DataProviderRegistry.register("crypto", CryptoProvider)

    # Create a provider by market name.
    provider = DataProviderRegistry.create("metals")
"""

from __future__ import annotations

import os
from typing import Dict, Type

from pyrobot.data.base import MarketDataProvider
from pyrobot.logging_config import get_logger

logger = get_logger("data_registry")


class DataProviderRegistry:
    """Central registry for market data providers.

    Each market (us, metals, crypto) maps to a MarketDataProvider class.
    The registry supports creation by name with optional kwargs.
    """

    _registry: Dict[str, Type[MarketDataProvider]] = {}

    @classmethod
    def register(cls, market: str, provider_class: Type[MarketDataProvider]) -> None:
        """Register a data provider class for a market."""
        if not issubclass(provider_class, MarketDataProvider):
            raise TypeError(
                f"{provider_class.__name__} must subclass MarketDataProvider"
            )
        cls._registry[market.lower()] = provider_class
        logger.info("Registered data provider: %s -> %s", market, provider_class.__name__)

    @classmethod
    def create(cls, market: str, **kwargs) -> MarketDataProvider:
        """Create a provider instance for the given market."""
        market_key = market.lower()
        if market_key not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"No data provider registered for market '{market}'. "
                f"Available: {available}"
            )
        provider_class = cls._registry[market_key]
        return provider_class(**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        """List registered market names."""
        return list(cls._registry.keys())

    @classmethod
    def get_class(cls, market: str) -> Type[MarketDataProvider]:
        """Get the provider class for a market (without instantiation)."""
        market_key = market.lower()
        if market_key not in cls._registry:
            raise ValueError(f"No data provider registered for market '{market}'")
        return cls._registry[market_key]

    @classmethod
    def clear(cls) -> None:
        """Remove all registrations (for testing)."""
        cls._registry.clear()


def register_builtin_data_providers() -> None:
    """Register the built-in market data providers into DataProviderRegistry.

    Lazy imports keep backtest-only code paths from loading yfinance/Alpaca
    SDKs when they never touch the registry.
    """
    if DataProviderRegistry.available():
        return
    from pyrobot.data.alpaca import AlpacaDataProvider
    from pyrobot.data.crypto_provider import CryptoProvider
    from pyrobot.data.metals_provider import MetalsProvider

    DataProviderRegistry.register("us", AlpacaDataProvider)
    DataProviderRegistry.register("metals", MetalsProvider)
    DataProviderRegistry.register("crypto", CryptoProvider)


def get_market_from_env() -> str:
    """Read the current market from the PYROBOT_MARKET environment variable."""
    return os.environ.get("PYROBOT_MARKET", "us").lower()
