"""Comprehensive Quantitative and Risk Performance Metrics."""

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np


@dataclass
class QuantitativeReport:
    """Detailed quantitative and risk performance summary."""

    total_return_pct: float
    cagr_pct: float
    annualized_volatility_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    ulcer_index: float
    var_95_daily_pct: float
    cvar_95_daily_pct: float
    win_rate_pct: float
    profit_factor: float
    expectancy_per_trade: float
    total_trades: int
    avg_win: float
    avg_loss: float
    max_consecutive_losses: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_return_pct": round(self.total_return_pct, 2),
            "cagr_pct": round(self.cagr_pct, 2),
            "annualized_volatility_pct": round(self.annualized_volatility_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "ulcer_index": round(self.ulcer_index, 4),
            "var_95_daily_pct": round(self.var_95_daily_pct, 2),
            "cvar_95_daily_pct": round(self.cvar_95_daily_pct, 2),
            "win_rate_pct": round(self.win_rate_pct, 2),
            "profit_factor": round(self.profit_factor, 4) if self.profit_factor != float("inf") else "inf",
            "expectancy_per_trade": round(self.expectancy_per_trade, 2),
            "total_trades": self.total_trades,
            "avg_win": round(self.avg_win, 2),
            "avg_loss": round(self.avg_loss, 2),
            "max_consecutive_losses": self.max_consecutive_losses,
        }


def calculate_quantitative_metrics(
    daily_returns: List[float],
    equity_curve: List[float],
    trades: List[Dict[str, Any]],
    risk_free_rate: float = 0.04,
    periods_per_year: int = 252,
) -> QuantitativeReport:
    """Compute institutional-grade quantitative metrics.

    Args:
        daily_returns: Per-period returns (period = one bar of the strategy's data).
        equity_curve: Mark-to-market equity per period.
        trades: Trade dicts with a 'pnl' key.
        risk_free_rate: Annual risk-free rate.
        periods_per_year: Bars per year for annualization (252 daily, 252*390 minute,
            ...). Must match the data frequency or Sharpe/CAGR/vol will be wrong.
    """
    if not daily_returns or len(daily_returns) < 2:
        return QuantitativeReport(
            total_return_pct=0.0,
            cagr_pct=0.0,
            annualized_volatility_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown_pct=0.0,
            ulcer_index=0.0,
            var_95_daily_pct=0.0,
            cvar_95_daily_pct=0.0,
            win_rate_pct=0.0,
            profit_factor=0.0,
            expectancy_per_trade=0.0,
            total_trades=len(trades),
            avg_win=0.0,
            avg_loss=0.0,
            max_consecutive_losses=0,
        )

    returns = np.array(daily_returns)
    equity = np.array(equity_curve)
    n_periods = len(returns)
    ppy = float(periods_per_year)

    # 1. Return & CAGR
    start_eq = equity[0]
    end_eq = equity[-1]
    total_ret = (end_eq - start_eq) / start_eq if start_eq > 0 else 0.0
    years = max(n_periods / ppy, 1.0 / ppy)
    cagr = ((end_eq / start_eq) ** (1.0 / years) - 1.0) if start_eq > 0 and end_eq > 0 else 0.0

    # 2. Volatility (Annualized)
    ann_vol = float(returns.std() * np.sqrt(ppy))

    # 3. Sharpe & Sortino
    rf_per_period = risk_free_rate / ppy
    excess_returns = returns - rf_per_period
    sharpe = float(np.sqrt(ppy) * excess_returns.mean() / returns.std()) if returns.std() > 0 else 0.0

    downside = returns[returns < 0]
    sortino = float(np.sqrt(ppy) * excess_returns.mean() / downside.std()) if len(downside) > 0 and downside.std() > 0 else 0.0

    # 4. Drawdown & Calmar
    peak = np.maximum.accumulate(equity)
    drawdowns = (equity - peak) / peak
    max_dd = float(abs(drawdowns.min())) if len(drawdowns) > 0 else 0.0
    calmar = (cagr / max_dd) if max_dd > 0 else 0.0

    # 5. Ulcer Index (measures depth and duration of drawdowns)
    # UI = sqrt( mean( (Drawdown_pct)^2 ) )
    ulcer_index = float(np.sqrt(np.mean((drawdowns * 100.0) ** 2)))

    # 6. VaR & CVaR (Historical 95% Daily)
    var_95 = float(abs(np.percentile(returns, 5)))
    cvar_tail = returns[returns <= -var_95]
    cvar_95 = float(abs(cvar_tail.mean())) if len(cvar_tail) > 0 else var_95

    # 7. Trade-level statistics
    pnls = [t.get("pnl", 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = (len(wins) / len(pnls) * 100.0) if pnls else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(abs(np.mean(losses))) if losses else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    expectancy = ((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss)

    # 8. Max Consecutive Losses
    max_streak = 0
    current_streak = 0
    for p in pnls:
        if p < 0:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0

    return QuantitativeReport(
        total_return_pct=total_ret * 100.0,
        cagr_pct=cagr * 100.0,
        annualized_volatility_pct=ann_vol * 100.0,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        max_drawdown_pct=max_dd * 100.0,
        ulcer_index=ulcer_index,
        var_95_daily_pct=var_95 * 100.0,
        cvar_95_daily_pct=cvar_95 * 100.0,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        expectancy_per_trade=expectancy,
        total_trades=len(trades),
        avg_win=avg_win,
        avg_loss=avg_loss,
        max_consecutive_losses=max_streak,
    )
