"""Realistic Execution Cost and Market Microstructure Model."""

from dataclasses import dataclass
import numpy as np


@dataclass
class CostModelConfig:
    """Configuration for transaction costs, spread, slippage, and market impact."""

    half_spread_bps: float = 2.0         # Half bid-ask spread in basis points (1 bp = 0.01% = 0.0001)
    base_slippage_bps: float = 3.0       # Base execution slippage in bps
    volatility_slippage_factor: float = 0.5  # Scale factor for realized volatility impact
    commission_per_share: float = 0.005  # Standard equity broker commission per share ($0.005/share)
    min_commission: float = 1.0          # Minimum commission per ticket
    sec_fee_rate: float = 0.0000278      # SEC transaction fee rate on sells
    market_impact_coefficient: float = 0.1 # Temporary price impact coefficient (Almgren-Chriss style)
    max_volume_participation: float = 0.10 # Maximum percentage of bar volume allowed to fill


class ExecutionCostModel:
    """Computes realistic execution prices and trading fees."""

    def __init__(self, config: CostModelConfig | None = None) -> None:
        self.config = config or CostModelConfig()

    def calculate_fill(
        self,
        side: str,                  # "BUY" or "SELL"
        quantity: float,
        price: float,
        bar_volume: float = 100000.0,
        volatility: float = 0.015,
    ) -> dict:
        """Calculate effective fill price, filled quantity, and all transaction fees.

        Returns:
            dict containing:
                - fill_price: float
                - filled_qty: float
                - slippage_cost: float
                - spread_cost: float
                - market_impact: float
                - total_commission: float
                - sec_fee: float
                - total_cost: float
        """
        side = side.upper()
        if quantity <= 0 or price <= 0:
            return {
                "fill_price": price,
                "filled_qty": 0.0,
                "slippage_cost": 0.0,
                "spread_cost": 0.0,
                "market_impact": 0.0,
                "total_commission": 0.0,
                "sec_fee": 0.0,
                "total_cost": 0.0,
            }

        # 1. Volume participation and partial fill constraint
        max_fillable = max(1.0, bar_volume * self.config.max_volume_participation)
        filled_qty = min(quantity, max_fillable)
        participation_rate = filled_qty / max(bar_volume, 1.0)

        # 2. Spread cost (Half spread paid on entry and exit)
        half_spread_pct = (self.config.half_spread_bps / 10000.0)
        spread_impact = price * half_spread_pct

        # 3. Dynamic Volatility-adjusted Slippage
        vol_multiplier = 1.0 + (self.config.volatility_slippage_factor * max(0.0, volatility / 0.01))
        slippage_pct = (self.config.base_slippage_bps / 10000.0) * vol_multiplier
        slippage_impact = price * slippage_pct

        # 4. Market Impact (Square root model)
        # Impact = price * eta * sqrt(order_qty / bar_volume)
        impact_pct = self.config.market_impact_coefficient * np.sqrt(participation_rate)
        market_impact = price * impact_pct

        # 5. Total price displacement
        total_price_delta = spread_impact + slippage_impact + market_impact
        if side in ("BUY", "BUY_TO_COVER"):
            effective_fill_price = price + total_price_delta
        else:
            effective_fill_price = max(0.01, price - total_price_delta)

        # 6. Commission & Regulatory Fees
        commission = max(self.config.min_commission, filled_qty * self.config.commission_per_share)
        sec_fee = (filled_qty * effective_fill_price * self.config.sec_fee_rate) if side in ("SELL", "SELL_SHORT") else 0.0
        total_fees = commission + sec_fee
        total_cost = (abs(effective_fill_price - price) * filled_qty) + total_fees

        return {
            "fill_price": round(effective_fill_price, 4),
            "filled_qty": filled_qty,
            "slippage_cost": round(slippage_impact * filled_qty, 4),
            "spread_cost": round(spread_impact * filled_qty, 4),
            "market_impact": round(market_impact * filled_qty, 4),
            "total_commission": round(commission, 4),
            "sec_fee": round(sec_fee, 4),
            "total_cost": round(total_cost, 4),
        }
