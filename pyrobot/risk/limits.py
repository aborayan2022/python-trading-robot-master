"""Risk Limits — configurable risk parameters for the trading platform.

All limits are defined as dataclass instances so they can be serialized,
validated, and hot-reloaded without restarting the system.

Usage::

    limits = RiskLimits(
        max_position_size_pct=0.05,
        max_daily_loss_pct=0.02,
        max_drawdown_pct=0.10,
    )

    if order_value > limits.max_single_order_value:
        raise PositionLimitError(...)
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class RiskLimits:
    """Central configuration for all risk management parameters.

    Attributes:
        max_position_size_pct: Maximum fraction of portfolio value for a
            single position (0.05 = 5%).
        max_single_order_value: Maximum dollar value for a single order.
            Set to 0 to disable.
        max_portfolio_exposure_pct: Maximum total long + short exposure as
            fraction of portfolio value (1.0 = 100%).
        max_long_exposure_pct: Maximum long exposure as fraction of portfolio.
        max_short_exposure_pct: Maximum short exposure as fraction of portfolio.
        max_daily_loss_pct: Maximum portfolio loss as fraction before kill switch.
        max_drawdown_pct: Maximum peak-to-trough drawdown before kill switch.
        max_sector_concentration_pct: Maximum exposure to a single sector.
        max_symbol_count: Maximum number of distinct symbols held.
        max_correlation_threshold: Maximum pairwise correlation between positions.
        max_volatility_threshold: Maximum portfolio volatility (annualized).
        cooldown_after_kill_switch_seconds: Seconds to wait after kill switch
            reset before allowing new orders.
        min_order_interval_seconds: Minimum seconds between orders for the
            same symbol.
        circuit_breaker_loss_streak: Number of consecutive losses before
            circuit breaker activates.
        circuit_breaker_drawdown_pct: Drawdown threshold for circuit breaker.
        default_stop_distance_pct: Default stop distance as a fraction of
            entry price (0.02 = 2%) used by fixed-fraction position sizing.
        per_trade_risk_pct: Fraction of equity to risk per trade for
            fixed-fraction sizing. When None (default), falls back to
            max_daily_loss_pct / 2 (half the daily loss budget per trade).
    """

    # Per-order limits
    max_position_size_pct: float = 0.05
    max_single_order_value: float = 100_000.0

    # Portfolio-level limits
    max_portfolio_exposure_pct: float = 1.5
    max_long_exposure_pct: float = 1.0
    max_short_exposure_pct: float = 0.3

    # Loss limits
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.10

    # Concentration limits
    max_sector_concentration_pct: float = 0.25
    max_symbol_count: int = 50
    max_correlation_threshold: float = 0.85

    # Volatility limits
    max_volatility_threshold: float = 0.50

    # Throttle limits
    cooldown_after_kill_switch_seconds: int = 300
    min_order_interval_seconds: int = 5

    # Circuit breaker
    circuit_breaker_loss_streak: int = 5
    circuit_breaker_drawdown_pct: float = 0.05

    # Position sizing defaults
    default_stop_distance_pct: float = 0.02
    per_trade_risk_pct: Optional[float] = None

    # Per-symbol overrides: symbol → override values
    symbol_overrides: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def get_symbol_limit(self, symbol: str, limit_name: str) -> Optional[float]:
        """Return the limit for a specific symbol, or None if no override."""
        overrides = self.symbol_overrides.get(symbol, {})
        return overrides.get(limit_name)

    def validate(self) -> None:
        """Validate that all limits are within sane bounds.

        Raises:
            ValueError: If any limit is negative or logically inconsistent.
        """
        if self.max_position_size_pct <= 0 or self.max_position_size_pct > 1.0:
            raise ValueError(
                f"max_position_size_pct must be in (0, 1.0], got {self.max_position_size_pct}"
            )
        if self.max_daily_loss_pct <= 0 or self.max_daily_loss_pct > 0.50:
            raise ValueError(
                f"max_daily_loss_pct must be in (0, 0.50], got {self.max_daily_loss_pct}"
            )
        if self.max_drawdown_pct <= 0 or self.max_drawdown_pct > 1.0:
            raise ValueError(
                f"max_drawdown_pct must be in (0, 1.0], got {self.max_drawdown_pct}"
            )
        if self.max_portfolio_exposure_pct <= 0:
            raise ValueError(
                f"max_portfolio_exposure_pct must be positive, got {self.max_portfolio_exposure_pct}"
            )
        if self.max_sector_concentration_pct <= 0 or self.max_sector_concentration_pct > 1.0:
            raise ValueError(
                f"max_sector_concentration_pct must be in (0, 1.0], got {self.max_sector_concentration_pct}"
            )
        if self.max_correlation_threshold < 0 or self.max_correlation_threshold > 1.0:
            raise ValueError(
                f"max_correlation_threshold must be in [0, 1.0], got {self.max_correlation_threshold}"
            )
        if self.max_symbol_count < 0:
            raise ValueError(
                f"max_symbol_count must be non-negative, got {self.max_symbol_count}"
            )
        if self.default_stop_distance_pct <= 0 or self.default_stop_distance_pct >= 1.0:
            raise ValueError(
                "default_stop_distance_pct must be in (0, 1.0), got "
                f"{self.default_stop_distance_pct}"
            )
        if self.per_trade_risk_pct is not None and (
            self.per_trade_risk_pct <= 0 or self.per_trade_risk_pct > 0.50
        ):
            raise ValueError(
                f"per_trade_risk_pct must be in (0, 0.50] or None, got "
                f"{self.per_trade_risk_pct}"
            )

    def to_dict(self) -> Dict:
        """Serialize limits to a dictionary."""
        return {
            "max_position_size_pct": self.max_position_size_pct,
            "max_single_order_value": self.max_single_order_value,
            "max_portfolio_exposure_pct": self.max_portfolio_exposure_pct,
            "max_long_exposure_pct": self.max_long_exposure_pct,
            "max_short_exposure_pct": self.max_short_exposure_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_sector_concentration_pct": self.max_sector_concentration_pct,
            "max_symbol_count": self.max_symbol_count,
            "max_correlation_threshold": self.max_correlation_threshold,
            "max_volatility_threshold": self.max_volatility_threshold,
            "cooldown_after_kill_switch_seconds": self.cooldown_after_kill_switch_seconds,
            "min_order_interval_seconds": self.min_order_interval_seconds,
            "circuit_breaker_loss_streak": self.circuit_breaker_loss_streak,
            "circuit_breaker_drawdown_pct": self.circuit_breaker_drawdown_pct,
            "default_stop_distance_pct": self.default_stop_distance_pct,
            "per_trade_risk_pct": self.per_trade_risk_pct,
            "symbol_overrides": self.symbol_overrides,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "RiskLimits":
        """Create RiskLimits from a dictionary, ignoring unknown keys."""
        known_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_keys}
        return cls(**filtered)

    @classmethod
    def conservative(cls) -> "RiskLimits":
        """Factory for conservative risk settings."""
        return cls(
            max_position_size_pct=0.02,
            max_single_order_value=25_000.0,
            max_portfolio_exposure_pct=1.0,
            max_daily_loss_pct=0.01,
            max_drawdown_pct=0.05,
            max_sector_concentration_pct=0.15,
            max_symbol_count=20,
            max_correlation_threshold=0.70,
            circuit_breaker_loss_streak=3,
            circuit_breaker_drawdown_pct=0.03,
        )

    @classmethod
    def aggressive(cls) -> "RiskLimits":
        """Factory for aggressive risk settings."""
        return cls(
            max_position_size_pct=0.10,
            max_single_order_value=250_000.0,
            max_portfolio_exposure_pct=2.0,
            max_long_exposure_pct=1.5,
            max_short_exposure_pct=0.5,
            max_daily_loss_pct=0.05,
            max_drawdown_pct=0.15,
            max_sector_concentration_pct=0.40,
            max_symbol_count=100,
            max_correlation_threshold=0.90,
            circuit_breaker_loss_streak=8,
            circuit_breaker_drawdown_pct=0.08,
        )
