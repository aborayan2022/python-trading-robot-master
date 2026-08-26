"""Position Sizer — Kelly Criterion and fixed-fraction position sizing.

Provides multiple sizing algorithms to determine optimal order quantities
based on account equity, risk parameters, and signal confidence.

The ``confidence`` input **must** be derived from calibrated probabilities
(see ``pyrobot.ai.calibration.IsotonicCalibrator`` and WO-1).  In the
standard pipeline ``confidence = |p_calibrated − 0.5| × 2`` where
``p_calibrated`` is the output of the ensemble engine's calibrator-transformed
direction probability.  Kelly sizing additionally requires realized
``win_rate``, ``avg_win``, and ``avg_loss`` from trade history — never
placeholders.  The fixed-fraction path uses only ``confidence`` for scaling.

Usage::

    sizer = PositionSizer(limits=RiskLimits())

    # Kelly Criterion sizing (requires real trade history)
    qty = sizer.kelly_size(
        account_equity=100_000.0,
        win_rate=0.55,        # from realized trade history
        avg_win=0.03,         # from realized trade history
        avg_loss=0.02,        # from realized trade history
        price=150.0,
        confidence=0.8,       # from calibrated probability
    )

    # Fixed-fraction sizing
    qty = sizer.fixed_fraction_size(
        account_equity=100_000.0,
        risk_per_trade_pct=0.01,
        stop_distance=5.0,
        price=150.0,
        confidence=0.8,       # from calibrated probability
    )
"""


from pyrobot.logging_config import get_logger
from pyrobot.risk.limits import RiskLimits

logger = get_logger("position_sizer")


class PositionSizer:
    """Position sizing engine with multiple algorithms.

    Args:
        limits: RiskLimits configuration.
        kelly_fraction: Fraction of full Kelly to use (0.5 = half-Kelly).
            Full Kelly is theoretically optimal but extremely volatile.
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        kelly_fraction: float = 0.5,
    ) -> None:
        self._limits = limits or RiskLimits()
        self._kelly_fraction = max(0.0, min(1.0, kelly_fraction))

    def kelly_size(
        self,
        account_equity: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        price: float,
        confidence: float = 1.0,
    ) -> int:
        """Calculate position size using the Kelly Criterion.

        The Kelly fraction is::

            f* = (p * b - q) / b

        where p = win probability, q = 1 - p, b = avg_win / avg_loss.

        We then apply kelly_fraction (default half-Kelly) and confidence scaling.

        **Important:** ``win_rate``, ``avg_win``, and ``avg_loss`` must come
        from realized trade history, never from placeholders.  ``confidence``
        must be derived from calibrated probabilities (see WO-1).

        Args:
            account_equity: Current portfolio equity in dollars.
            win_rate: Historical win rate (0.0 to 1.0) — from trade history.
            avg_win: Average winning trade return (as decimal, e.g. 0.03 for 3%).
            avg_loss: Average losing trade return (as decimal, must be positive).
            price: Current market price per share.
            confidence: Signal confidence (0.0 to 1.0), from calibrated probabilities.

        Returns:
            Number of shares (rounded down, minimum 0).
        """
        if price <= 0 or account_equity <= 0:
            return 0

        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1.0:
            return 0

        b = avg_win / avg_loss
        p = win_rate
        q = 1.0 - p

        kelly_f = (p * b - q) / b
        if kelly_f <= 0:
            logger.info(
                "Kelly fraction negative (%.4f) — no position recommended", kelly_f
            )
            return 0

        # Apply fraction and confidence
        adjusted_f = kelly_f * self._kelly_fraction * confidence

        # Dollar amount to risk
        dollar_risk = account_equity * adjusted_f

        # Convert to shares
        qty = int(dollar_risk / price)

        # Apply per-order value limit
        qty = self._apply_value_limit(qty, price)

        logger.info(
            "Kelly sizing: f_raw=%.4f f_adj=%.4f dollar_risk=%.0f qty=%d",
            kelly_f, adjusted_f, dollar_risk, qty,
        )
        return max(0, qty)

    def fixed_fraction_size(
        self,
        account_equity: float,
        risk_per_trade_pct: float,
        stop_distance: float,
        price: float,
        confidence: float = 1.0,
    ) -> int:
        """Calculate position size using fixed-fraction risk per trade.

        Position size = (equity * risk_pct * confidence) / stop_distance

        ``confidence`` must be derived from calibrated probabilities (WO-1):
        ``confidence = |p_calibrated − 0.5| × 2``.

        Args:
            account_equity: Current portfolio equity in dollars.
            risk_per_trade_pct: Fraction of equity to risk per trade (e.g. 0.01 = 1%).
            stop_distance: Distance from entry to stop loss in dollars per share.
            price: Current market price per share.
            confidence: Signal confidence (0.0 to 1.0), from calibrated probabilities.

        Returns:
            Number of shares (rounded down, minimum 0).
        """
        if price <= 0 or account_equity <= 0 or stop_distance <= 0:
            return 0

        dollar_risk = account_equity * risk_per_trade_pct * confidence
        qty = int(dollar_risk / stop_distance)

        qty = self._apply_value_limit(qty, price)

        logger.info(
            "Fixed-fraction sizing: risk_pct=%.4f stop_dist=%.2f dollar_risk=%.0f qty=%d",
            risk_per_trade_pct, stop_distance, dollar_risk, qty,
        )
        return max(0, qty)

    def target_weight_size(
        self,
        account_equity: float,
        current_quantity: float,
        target_weight: float,
        price: float,
    ) -> int:
        """Calculate shares needed to reach a target portfolio weight.

        Args:
            account_equity: Current portfolio equity in dollars.
            current_quantity: Current number of shares held (can be negative for shorts).
            target_weight: Desired fraction of equity (e.g. 0.05 for 5%).
            price: Current market price per share.

        Returns:
            Number of shares to trade (positive = buy, negative = sell).
            Returns 0 if adjustment is less than 1 share.
        """
        if price <= 0 or account_equity <= 0:
            return 0

        target_value = account_equity * target_weight
        target_qty = target_value / price
        adjustment = target_qty - current_quantity

        if abs(adjustment) < 1.0:
            return 0

        return int(adjustment)

    def volatility_target_size(
        self,
        account_equity: float,
        target_volatility: float,
        realized_volatility: float,
        current_quantity: float,
        price: float,
    ) -> int:
        """Calculate position size targeting a specific volatility contribution.

        Uses the formula:
            target_qty = (target_vol / realized_vol) * current_qty

        Args:
            account_equity: Current portfolio equity in dollars.
            target_volatility: Desired annualized volatility for this position.
            realized_volatility: Current annualized volatility of the asset.
            current_quantity: Current number of shares held.
            price: Current market price per share.

        Returns:
            Target number of shares to hold (not the trade quantity).
        """
        if price <= 0 or realized_volatility <= 0 or account_equity <= 0:
            return 0

        vol_scalar = target_volatility / realized_volatility
        target_qty = int(vol_scalar * current_quantity)

        # Apply per-order value limit
        target_qty = self._apply_value_limit(target_qty, price)

        return max(0, target_qty)

    def _apply_value_limit(self, qty: int, price: float) -> int:
        """Cap quantity to the max_single_order_value limit."""
        max_value = self._limits.max_single_order_value
        if max_value <= 0:
            return qty

        max_qty = int(max_value / price) if price > 0 else 0
        return min(qty, max_qty)
