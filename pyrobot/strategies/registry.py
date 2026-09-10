"""Strategy Registry — factory pattern for creating strategy instances by name.

Decouples strategy selection from pipeline construction. Strategies register
themselves at import time, and the registry creates instances by name.

Usage::

    from pyrobot.strategies.registry import StrategyRegistry

    # Register (done in each strategy module or at __init__.py import time)
    StrategyRegistry.register("us_trend", USTrendFollowStrategy)
    StrategyRegistry.register("us_mean_reversion", USMeanReversionStrategy)

    # Create by name
    strategy = StrategyRegistry.create("us_trend", symbols=["AAPL", "MSFT"])

    # Create from environment variable
    strategy = StrategyRegistry.create_from_env(symbols=["AAPL", "MSFT"])

Environment:
    PYROBOT_STRATEGY  strategy name to create (default "us_trend")
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Type

from pyrobot.logging_config import get_logger
from pyrobot.strategies.base import BaseStrategy

logger = get_logger("strategy_registry")


class StrategyRegistry:
    """Factory for creating strategy instances by name.

    Each strategy class registers itself via ``StrategyRegistry.register(name, cls)``.
    The registry stores the mapping and creates instances on demand.
    """

    _registry: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, name: str, strategy_class: Type[BaseStrategy]) -> None:
        """Register a strategy class under a given name.

        Args:
            name: Short name used for selection (e.g., "us_trend").
            strategy_class: A subclass of BaseStrategy.

        Raises:
            TypeError: If strategy_class is not a BaseStrategy subclass.
        """
        if not (isinstance(strategy_class, type) and issubclass(strategy_class, BaseStrategy)):
            raise TypeError(
                f"{strategy_class} must be a subclass of BaseStrategy"
            )
        cls._registry[name.lower()] = strategy_class
        logger.info("Registered strategy: %s -> %s", name, strategy_class.__name__)

    @classmethod
    def create(
        cls,
        name: str,
        symbols: List[str],
        parameters: Optional[Dict[str, Any]] = None,
        strategy_id: Optional[str] = None,
    ) -> BaseStrategy:
        """Create a strategy instance by name.

        Args:
            name: Registered strategy name (case-insensitive).
            symbols: List of ticker symbols to trade.
            parameters: Optional parameter overrides.
            strategy_id: Optional custom strategy ID (defaults to name).

        Returns:
            Initialized strategy instance.

        Raises:
            ValueError: If name is not registered.
        """
        key = name.lower()
        if key not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"Unknown strategy: '{name}'. Available: {available}"
            )
        strategy_class = cls._registry[key]
        sid = strategy_id or key
        return strategy_class(
            strategy_id=sid,
            symbols=symbols,
            parameters=parameters,
        )

    @classmethod
    def create_from_env(
        cls,
        symbols: List[str],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> BaseStrategy:
        """Create a strategy from the PYROBOT_STRATEGY environment variable.

        Defaults to "us_trend" if the variable is not set.
        """
        name = os.environ.get("PYROBOT_STRATEGY", "us_trend")
        return cls.create(name, symbols, parameters)

    @classmethod
    def available(cls) -> List[str]:
        """List all registered strategy names."""
        return sorted(cls._registry.keys())

    @classmethod
    def get_class(cls, name: str) -> Type[BaseStrategy]:
        """Get the strategy class without instantiation."""
        key = name.lower()
        if key not in cls._registry:
            raise ValueError(f"Unknown strategy: '{name}'")
        return cls._registry[key]

    @classmethod
    def clear(cls) -> None:
        """Remove all registrations (for testing)."""
        cls._registry.clear()
