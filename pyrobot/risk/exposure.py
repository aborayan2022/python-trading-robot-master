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

    if not monitor.check_order(
        exposure, "TSLA", "BUY", 100, 200.0, 100_000.0, positions=positions
    ):
        raise ExposureLimitError(...)
"""

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from pyrobot.logging_config import get_logger
from pyrobot.risk.limits import RiskLimits

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
        volatility_by_symbol: Optional mapping of symbol → annualized
            volatility. When provided (and the symbol is present), orders
            are rejected if the volatility exceeds
            limits.max_volatility_threshold.
        correlation_matrix: Optional symmetric DataFrame of pairwise
            symbol correlations. When provided together with current
            positions, an order is rejected if the symbol's absolute
            correlation with any currently held symbol exceeds
            limits.max_correlation_threshold.
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        sector_map: Dict[str, str] | None = None,
        volatility_by_symbol: Dict[str, float] | None = None,
        correlation_matrix: Optional[pd.DataFrame] = None,
    ) -> None:
        self._limits = limits or RiskLimits()
        self._sector_map = sector_map or {}
        self._volatility_by_symbol = volatility_by_symbol
        self._correlation_matrix = correlation_matrix

    def set_volatility_by_symbol(
        self, volatility_by_symbol: Dict[str, float] | None
    ) -> None:
        """Set or clear the per-symbol volatility map.

        Args:
            volatility_by_symbol: Symbol → annualized volatility, or None
                to disable volatility enforcement.
        """
        self._volatility_by_symbol = volatility_by_symbol

    def set_correlation_matrix(self, correlation_matrix: pd.DataFrame | None) -> None:
        """Set or clear the pairwise correlation matrix.

        Args:
            correlation_matrix: Symmetric DataFrame indexed by symbol on
                both axes, or None to disable correlation enforcement.
        """
        self._correlation_matrix = correlation_matrix

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
        positions: Dict[str, float] | None = None,
    ) -> tuple[bool, str]:
        """Check if an order would breach exposure limits.

        Orders are projected against current holdings so that risk-reducing
        orders are not penalized: a SELL against an existing long reduces
        long exposure (only the excess beyond the holding opens short), a
        BUY against an existing short covers it (only the excess adds
        long).

        Args:
            current_exposure: Current ExposureSnapshot.
            symbol: Ticker symbol for the new order.
            side: "BUY" or "SELL".
            quantity: Order quantity.
            price: Order price per share.
            account_equity: Total portfolio equity.
            positions: Current holdings (symbol → quantity, positive =
                long, negative = short). When omitted, the projection
                falls back to portfolio-level long/short totals.

        Returns:
            Tuple of (is_allowed, reason_string).
        """
        order_value = quantity * price
        is_buy = side in ("BUY", "BUY_TO_COVER")

        (
            new_long,
            new_short,
            new_symbol_count,
            sector_delta,
            exposure_increase,
        ) = self._project_order(
            current_exposure, symbol, order_value, price, is_buy, positions
        )

        equity = max(account_equity, 1.0)

        # Check gross exposure
        gross_pct = (new_long + new_short) / equity
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

        # Check per-symbol position size limit — only the exposure-
        # increasing portion counts (closing/covering orders reduce risk).
        pos_size_pct = exposure_increase / equity
        if pos_size_pct > self._limits.max_position_size_pct:
            return False, (
                f"Position size {pos_size_pct:.2%} of equity would exceed limit "
                f"{self._limits.max_position_size_pct:.2%}"
            )

        # Check sector concentration — only the exposure-increasing side
        # adds; reductions release concentration headroom.
        sector = self._sector_map.get(symbol, "UNKNOWN")
        current_sector = current_exposure.sector_exposure.get(sector, 0.0)
        new_sector_value = max(current_sector + sector_delta, 0.0)
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

        # Check per-symbol volatility limit
        vol_rejection = self._check_volatility(symbol)
        if vol_rejection is not None:
            return False, vol_rejection

        # Check correlation against currently held symbols
        corr_rejection = self._check_correlation(symbol, positions)
        if corr_rejection is not None:
            return False, corr_rejection

        return True, "OK"

    def _project_order(
        self,
        current_exposure: ExposureSnapshot,
        symbol: str,
        order_value: float,
        price: float,
        is_buy: bool,
        positions: Dict[str, float] | None,
    ) -> tuple[float, float, int, float, float]:
        """Project portfolio state after an order executes.

        Args:
            current_exposure: Current ExposureSnapshot.
            symbol: Ticker symbol for the new order.
            order_value: Dollar value of the order (quantity * price).
            price: Order price per share.
            is_buy: True for BUY/BUY_TO_COVER, False for SELL/SELL_SHORT.
            positions: Current holdings, or None for the portfolio-level
                fallback projection.

        Returns:
            Tuple of (new_long_value, new_short_value, new_symbol_count,
            sector_delta, exposure_increase) where sector_delta is the
            change in the order symbol's sector exposure and
            exposure_increase is the portion of the order that adds
            gross exposure.
        """
        if positions is not None:
            held_qty = float(positions.get(symbol, 0.0))
            held_long_value = max(held_qty, 0.0) * price
            held_short_value = max(-held_qty, 0.0) * price
            symbol_held = held_qty != 0.0
        else:
            # No per-symbol data — fall back to portfolio-level totals so
            # closing orders are still recognized as risk-reducing.
            held_long_value = current_exposure.long_value
            held_short_value = current_exposure.short_value
            symbol_held = False

        if is_buy:
            # BUY against an existing short covers it first; only the
            # excess beyond the short adds long exposure.
            short_reduce = min(order_value, held_short_value)
            long_add = order_value - short_reduce
            long_reduce = 0.0
            short_add = 0.0
        else:
            # SELL against an existing long reduces it first; only the
            # excess beyond the holding opens short exposure.
            long_reduce = min(order_value, held_long_value)
            short_add = order_value - long_reduce
            short_reduce = 0.0
            long_add = 0.0

        new_long = max(current_exposure.long_value - long_reduce, 0.0) + long_add
        new_short = max(current_exposure.short_value - short_reduce, 0.0) + short_add

        new_symbol_count = current_exposure.symbol_count
        if is_buy and long_add > 0 and not symbol_held:
            new_symbol_count += 1

        sector_delta = (long_add + short_add) - (long_reduce + short_reduce)
        exposure_increase = long_add + short_add

        return new_long, new_short, new_symbol_count, sector_delta, exposure_increase

    def _check_volatility(self, symbol: str) -> Optional[str]:
        """Check the symbol's volatility against the configured limit.

        Args:
            symbol: Ticker symbol for the new order.

        Returns:
            Rejection reason string, or None if the order passes (or no
            volatility data is available).
        """
        if self._volatility_by_symbol is None:
            return None
        volatility = self._volatility_by_symbol.get(symbol)
        if volatility is None:
            return None
        if volatility > self._limits.max_volatility_threshold:
            return (
                f"Volatility {volatility:.2%} for {symbol} exceeds limit "
                f"{self._limits.max_volatility_threshold:.2%}"
            )
        return None

    def _check_correlation(
        self,
        symbol: str,
        positions: Dict[str, float] | None,
    ) -> Optional[str]:
        """Check correlation between the symbol and currently held symbols.

        Args:
            symbol: Ticker symbol for the new order.
            positions: Current holdings (used to determine held symbols).

        Returns:
            Rejection reason string, or None if the order passes (or no
            correlation matrix / positions are available).
        """
        if self._correlation_matrix is None or not positions:
            return None
        threshold = self._limits.max_correlation_threshold
        held_symbols = [s for s, q in positions.items() if q != 0 and s != symbol]
        for held_symbol in held_symbols:
            correlation = self._pair_correlation(symbol, held_symbol)
            if correlation is None:
                continue
            if abs(correlation) > threshold:
                return (
                    f"Correlation {correlation:.2f} between {symbol} and held "
                    f"{held_symbol} exceeds limit {threshold:.2f}"
                )
        return None

    def _pair_correlation(self, symbol: str, held_symbol: str) -> Optional[float]:
        """Look up the pairwise correlation for two symbols.

        Args:
            symbol: Ticker symbol for the new order.
            held_symbol: Currently held ticker symbol.

        Returns:
            Correlation coefficient, or None if unavailable in the matrix.
        """
        matrix = self._correlation_matrix
        if matrix is None:
            return None
        try:
            value = matrix.loc[symbol, held_symbol]
        except KeyError:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def __repr__(self) -> str:
        return (
            f"ExposureMonitor("
            f"max_gross={self._limits.max_portfolio_exposure_pct:.0%}, "
            f"max_long={self._limits.max_long_exposure_pct:.0%}, "
            f"max_short={self._limits.max_short_exposure_pct:.0%})"
        )
