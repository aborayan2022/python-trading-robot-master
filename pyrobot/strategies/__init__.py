"""Strategy Engine - base classes and built-in strategies."""

from pyrobot.strategies.base import (
    BaseStrategy,
    ExampleStrategy,
    MultiSymbolStrategy,
    StrategyState,
)
from pyrobot.strategies.registry import StrategyRegistry


def register_builtin_strategies() -> None:
    """Register all built-in strategies in the StrategyRegistry.

    Idempotent — safe to call at import time, after a registry test cleared
    the registry, or when reloading the strategy package.
    """
    try:
        from pyrobot.strategies.us_trend import USTrendFollowStrategy
        StrategyRegistry.register("us_trend", USTrendFollowStrategy)
    except Exception:
        pass

    try:
        from pyrobot.strategies.us_mean_reversion import USMeanReversionStrategy
        StrategyRegistry.register("us_mean_reversion", USMeanReversionStrategy)
    except Exception:
        pass

    try:
        from pyrobot.strategies.us_breakout import USBreakoutStrategy
        StrategyRegistry.register("us_breakout", USBreakoutStrategy)
    except Exception:
        pass

    try:
        from pyrobot.strategies.metals_trend import MetalsTrendFollowStrategy
        StrategyRegistry.register("metals_trend", MetalsTrendFollowStrategy)
    except Exception:
        pass

    try:
        from pyrobot.strategies.metals_momentum import MetalsMomentumBreakout
        StrategyRegistry.register("metals_momentum", MetalsMomentumBreakout)
    except Exception:
        pass

    try:
        from pyrobot.strategies.crypto_trend import CryptoTrendBreakoutStrategy
        StrategyRegistry.register("crypto_trend", CryptoTrendBreakoutStrategy)
    except Exception:
        pass

    try:
        from pyrobot.strategies.crypto_mean_rev import CryptoMeanReversionStrategy
        StrategyRegistry.register("crypto_mean_reversion", CryptoMeanReversionStrategy)
    except Exception:
        pass


register_builtin_strategies()

__all__ = [
    "StrategyState",
    "BaseStrategy",
    "MultiSymbolStrategy",
    "ExampleStrategy",
    "StrategyRegistry",
    "register_builtin_strategies",
]
