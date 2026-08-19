"""Exposure Monitor — tracks and enforces portfolio exposure limits.

Calculates long, short, net, and gross exposure in real-time and
triggers alerts or rejects orders that would breach configured limits.

Usage::

    monitor = ExposureMonitor(limits=RiskLimits())

    # Update with current positions
    positions = {"AAPL": 100, "MSFT": -50, "GOOG": 200}
    prices = {"AAPL": 180.0, "MSFT": 380.0, "GOOG": 140.0}

    exposure = monitor.calculate_exposure(
        positions=positions,
        prices=prices,
        account_equity=100_000.0,
    )

    if not monitor.check_order(exposure, "TSLA", "BUY", 100, 200.0, 100_000.0):
        raise ExposureLimitError(...)
"""

from dataclasses import dataclass
from typing import Dict

from pyrobot.risk.limits import RiskLimits
from pyrobot.logging_config import get_logger

logger = get_logger("exposure_monitor")


@dataclass
class ExposureSnapshot:
    """Current portfolio exposure metrics."""

    long_value: float
    short_value: float
    net_exposure: float    # long - short (signed)
    gross_exposure: float  # long + short (unsigned)
    long_exposure_pct: float
    short_exposure_pct: float
    gross_exposure_pct: float
    symbol_count: int
    sector_exposure: Dict[str, float]


class ExposureMonitor:
    """Real-time exposure monitoring and limit enforcement.

    Args:
        limits: RiskLimits configuration.
        sector_map: Optional mapping of symbol → sector name.
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        sector_map: Dict[str, str] | None = None,
    ) -> None:
        self._limits = limits or RiskLimits()
        self._sector_map = sector_map or {}

    def calculate_exposure(
        self,
        positions: Dict[str, float],
        prices: Dict[str, float],
        account_equity: float,
    ) -> ExposureSnapshot:
        """Calculate current portfolio exposure from positions and prices.

        Args:
            positions: Symbol → quantity (positive = long, negative = short).
            prices: Symbol → current market price.
            account_equity: Total portfolio equity in dollars.

        Returns:
            ExposureSnapshot with all exposure metrics.
        """
        long_value = 0.0
        short_value = 0.0
        sector_exposure: Dict[str, float] = {}

        for symbol, qty in positions.items():
            price = prices.get(symbol, 0.0)
            position_value = abs(qty * price)

            if qty > 0:
                long_value += position_value
            elif qty < 0:
                short_value += position_value

            # Track sector exposure
            sector = self._sector_map.get(symbol, "UNKNOWN")
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + position_value

        net = long_value - short_value
        gross = long_value + short_value

        equity = max(account_equity, 1.0)  # Avoid division by zero

        return ExposureSnapshot(
            long_value=long_value,
            short_value=short_value,
            net_exposure=net,
            gross_exposure=gross,
            long_exposure_pct=long_value / equity,
            short_exposure_pct=short_value / equity,
            gross_exposure_pct=gross / equity,
            symbol_count=len([q for q in positions.values() if q != 0]),
            sector_exposure=sector_exposure,
        )

    def check_order(
        self,
        current_exposure: ExposureSnapshot,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        account_equity: float,
    ) -> tuple[bool, str]:
        """Check if an order would breach exposure limits.

        Args:
            current_exposure: Current ExposureSnapshot.
            symbol: Ticker symbol for the new order.
            side: "BUY" or "SELL".
            quantity: Order quantity.
            price: Order price per share.
            account_equity: Total portfolio equity.

        Returns:
            Tuple of (is_allowed, reason_string).
        """
        order_value = quantity * price

        # Projected exposure after order
        if side in ("BUY", "BUY_TO_COVER"):
            new_long = current_exposure.long_value + order_value
            new_short = current_exposure.short_value
        else:  # SELL or SELL_SHORT
            new_long = current_exposure.long_value
            new_short = current_exposure.short_value + order_value

        new_gross = new_long + new_short
        new_symbol_count = current_exposure.symbol_count
        if side in ("BUY", "BUY_TO_COVER"):
            new_symbol_count += 1

        equity = max(account_equity, 1.0)

        # Check gross exposure
        gross_pct = new_gross / equity
        if gross_pct > self._limits.max_portfolio_exposure_pct:
            return False, (
                f"Gross exposure {gross_pct:.2%} would exceed limit "
                f"{self._limits.max_portfolio_exposure_pct:.2%}"
            )

        # Check long exposure
        long_pct = new_long / equity
        if long_pct > self._limits.max_long_exposure_pct:
            return False, (
                f"Long exposure {long_pct:.2%} would exceed limit "
                f"{self._limits.max_long_exposure_pct:.2%}"
            )

        # Check short exposure
        short_pct = new_short / equity
        if short_pct > self._limits.max_short_exposure_pct:
            return False, (
                f"Short exposure {short_pct:.2%} would exceed limit "
                f"{self._limits.max_short_exposure_pct:.2%}"
            )

        # Check symbol count
        if new_symbol_count > self._limits.max_symbol_count:
            return False, (
                f"Symbol count {new_symbol_count} would exceed limit "
                f"{self._limits.max_symbol_count}"
            )

        # Check per-symbol position size limit
        pos_size_pct = order_value / equity
        if pos_size_pct > self._limits.max_position_size_pct:
            return False, (
                f"Position size {pos_size_pct:.2%} of equity would exceed limit "
                f"{self._limits.max_position_size_pct:.2%}"
            )

        # Check sector concentration
        sector = self._sector_map.get(symbol, "UNKNOWN")
        current_sector = current_exposure.sector_exposure.get(sector, 0.0)
        new_sector_value = current_sector + order_value
        sector_pct = new_sector_value / equity
        if sector_pct > self._limits.max_sector_concentration_pct:
            return False, (
                f"Sector '{sector}' exposure {sector_pct:.2%} would exceed limit "
                f"{self._limits.max_sector_concentration_pct:.2%}"
            )

        # Check single order value
        if self._limits.max_single_order_value > 0:
            if order_value > self._limits.max_single_order_value:
                return False, (
                    f"Order value ${order_value:,.2f} exceeds max "
                    f"${self._limits.max_single_order_value:,.2f}"
                )

        return True, "OK"

    def __repr__(self) -> str:
        return (
            f"ExposureMonitor("
            f"max_gross={self._limits.max_portfolio_exposure_pct:.0%}, "
            f"max_long={self._limits.max_long_exposure_pct:.0%}, "
            f"max_short={self._limits.max_short_exposure_pct:.0%})"
        )
