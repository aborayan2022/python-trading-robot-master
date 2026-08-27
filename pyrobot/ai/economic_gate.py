"""WO-4: Economic approval gate — replay OOS signals through the honest backtester.

Reconstructs the trading signal sequence the deployed EnsembleSignalEngine
would have produced from a probability stream, then replays those signals
through BacktestEngine (next-bar execution + ExecutionCostModel) to produce
net PnL, annualized Sharpe, max drawdown, profit factor, and EV per trade.
"""

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

from pyrobot.backtesting.cost_model import ExecutionCostModel
from pyrobot.backtesting.engine import BacktestEngine
from pyrobot.logging_config import get_logger

logger = get_logger("economic_gate")


@dataclass
class EconomicMetrics:
    """Result of replaying a probability stream through the cost-aware backtester."""

    net_pnl_after_costs: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    n_trades: int = 0
    ev_per_trade: float = 0.0

    def to_dict(self) -> dict:
        return {
            "net_pnl_after_costs": self.net_pnl_after_costs,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "profit_factor": self.profit_factor,
            "n_trades": self.n_trades,
            "ev_per_trade": self.ev_per_trade,
        }


def evaluate_oos_economics(
    oos_probabilities: np.ndarray,
    aligned_prices: pd.DataFrame,
    min_probability: float = 0.80,
    exit_probability: float = 0.45,
    bar_type: str = "day",
    cost_model: Optional[ExecutionCostModel] = None,
    initial_balance: float = 100_000.0,
    position_size_fraction: float = 0.95,
) -> EconomicMetrics:
    """Reconstruct signals from an OOS probability stream and replay through the backtester.

    Args:
        oos_probabilities: Array of calibrated P(up) values, one per bar.
        aligned_prices: DataFrame with columns ``open``, ``high``, ``low``,
            ``close``, ``volume`` indexed to match the probability stream
            (same length, same ordering).
        min_probability: Long/short entry threshold (matches EnsembleSignalEngine).
        exit_probability: Exit threshold for open positions (matches engine).
        bar_type: Drives Sharpe annualization factor (``"day"`` → 252).
        cost_model: Execution cost model; defaults to standard CostModelConfig.
        initial_balance: Starting equity for the backtest replay.
        position_size_fraction: Fraction of equity deployed per entry.

    Returns:
        EconomicMetrics with all six fields populated.
    """
    n = len(oos_probabilities)
    if n == 0:
        logger.warning("Empty probability stream — returning zero economic metrics")
        return EconomicMetrics()

    prices = aligned_prices[["open", "high", "low", "close", "volume"]].copy()
    if len(prices) != n:
        raise ValueError(
            f"Probability stream ({n}) and price frame ({len(prices)}) length mismatch"
        )

    # ── Reconstruct signal sequence (mirrors ensemble.py lines 190-201) ──
    signals: List[Optional[str]] = [None] * n
    position = 0  # +1 long, -1 short, 0 flat

    for i in range(n):
        p = float(oos_probabilities[i])
        if position == 1 and p < exit_probability:
            signals[i] = "sell"
            position = 0
            continue
        if position == -1 and p > (1.0 - exit_probability):
            signals[i] = "buy"
            position = 0
            continue
        if p >= min_probability:
            signals[i] = "buy"
            position = 1
        elif p <= (1.0 - min_probability):
            signals[i] = "sell"
            position = -1
        # else: no signal, position unchanged (flat)

    # ── Build historical data list for BacktestEngine ──
    hist_data: List[dict] = []
    for i in range(n):
        row = prices.iloc[i]
        # Handle MultiIndex (symbol, datetime) — extract the datetime part.
        idx = prices.index[i]
        if isinstance(idx, tuple):
            dt_str = str(idx[1]) if len(idx) > 1 else str(i)
        elif hasattr(idx, "isoformat"):
            dt_str = str(idx)
        else:
            dt_str = str(i)
        hist_data.append({
            "symbol": "OOS_REPLAY",
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "datetime": dt_str,
        })

    # ── Wrap reconstructed signals in a strategy closure ──
    counter = {"n": 0}

    def strategy(stock_frame, indicator_client):
        idx = counter["n"]
        counter["n"] += 1
        return signals[idx] if idx < len(signals) else None

    # ── Run honest backtester ──
    engine_kwargs = {
        "initial_balance": initial_balance,
        "historical_data": hist_data,
        "position_size_fraction": position_size_fraction,
    }
    if cost_model is not None:
        engine_kwargs["cost_model"] = cost_model

    engine = BacktestEngine(**engine_kwargs)
    result = engine.run(strategy=strategy, bar_type=bar_type)

    # ── Extract metrics ──
    metrics = EconomicMetrics(
        net_pnl_after_costs=result.ending_balance - result.starting_balance,
        sharpe=result.sharpe_ratio,
        max_drawdown=result.max_drawdown,
        profit_factor=result.profit_factor,
        n_trades=result.total_trades,
    )
    metrics.ev_per_trade = (
        metrics.net_pnl_after_costs / metrics.n_trades
        if metrics.n_trades > 0
        else 0.0
    )

    logger.info(
        "Economic gate: n=%d, trades=%d, net_pnl=%.2f, sharpe=%.3f, ev/trade=%.2f",
        n, metrics.n_trades, metrics.net_pnl_after_costs,
        metrics.sharpe, metrics.ev_per_trade,
    )
    return metrics
