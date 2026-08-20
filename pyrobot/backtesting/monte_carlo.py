"""Monte Carlo Simulation for Strategy Stress Testing and Risk of Ruin."""

from dataclasses import dataclass
from typing import List, Dict, Any
import numpy as np


@dataclass
class MonteCarloReport:
    """Statistical distribution of strategy metrics under bootstrap / random reshuffling."""

    simulations: int
    median_return_pct: float
    p5_return_pct: float             # 5th percentile (stress-case return)
    p95_return_pct: float            # 95th percentile (optimistic return)
    median_max_drawdown_pct: float
    worst_case_drawdown_pct: float   # 99th percentile worst-case drawdown
    ruin_probability_pct: float      # Probability of losing > ruin_threshold_pct of capital
    median_sharpe: float
    p5_sharpe: float

    def summary(self) -> Dict[str, Any]:
        return {
            "simulations": self.simulations,
            "median_return_pct": round(self.median_return_pct, 2),
            "p5_return_pct (worst 5%)": round(self.p5_return_pct, 2),
            "p95_return_pct": round(self.p95_return_pct, 2),
            "median_max_drawdown_pct": round(self.median_max_drawdown_pct, 2),
            "worst_case_drawdown_pct (99th%)": round(self.worst_case_drawdown_pct, 2),
            "ruin_probability_pct": round(self.ruin_probability_pct, 2),
            "median_sharpe": round(self.median_sharpe, 4),
            "p5_sharpe": round(self.p5_sharpe, 4),
        }


class MonteCarloSimulator:
    """Runs bootstrap resampling and sequence randomization over trade lists."""

    def __init__(
        self,
        n_simulations: int = 1000,
        initial_capital: float = 100000.0,
        ruin_threshold_pct: float = 0.25, # e.g. Losing 25% of account
        seed: int | None = 42,
    ) -> None:
        self.n_simulations = n_simulations
        self.initial_capital = initial_capital
        self.ruin_threshold_pct = ruin_threshold_pct
        self.seed = seed

    def run(self, trades: List[Dict[str, Any]]) -> MonteCarloReport:
        """Run Monte Carlo simulation across trade PnLs."""
        if not trades:
            return MonteCarloReport(
                simulations=self.n_simulations,
                median_return_pct=0.0,
                p5_return_pct=0.0,
                p95_return_pct=0.0,
                median_max_drawdown_pct=0.0,
                worst_case_drawdown_pct=0.0,
                ruin_probability_pct=0.0,
                median_sharpe=0.0,
                p5_sharpe=0.0,
            )

        if self.seed is not None:
            np.random.seed(self.seed)

        pnls = np.array([t.get("pnl", 0.0) for t in trades])
        n_trades = len(pnls)

        sim_returns = []
        sim_drawdowns = []
        sim_sharpes = []
        ruined_count = 0

        for _ in range(self.n_simulations):
            # Resample with replacement
            sampled_pnls = np.random.choice(pnls, size=n_trades, replace=True)
            equity_curve = self.initial_capital + np.cumsum(sampled_pnls)
            equity_curve = np.insert(equity_curve, 0, self.initial_capital)

            # Return
            total_ret = (equity_curve[-1] - self.initial_capital) / self.initial_capital
            sim_returns.append(total_ret * 100.0)

            # Max Drawdown
            peak = np.maximum.accumulate(equity_curve)
            dd = (equity_curve - peak) / peak
            max_dd = float(abs(dd.min()))
            sim_drawdowns.append(max_dd * 100.0)

            # Ruin check
            if max_dd >= self.ruin_threshold_pct or np.any(equity_curve <= self.initial_capital * (1.0 - self.ruin_threshold_pct)):
                ruined_count += 1

            # Sharpe of trade returns
            trade_returns = sampled_pnls / self.initial_capital
            std = trade_returns.std()
            sharpe = (trade_returns.mean() / std * np.sqrt(252)) if std > 0 else 0.0
            sim_sharpes.append(sharpe)

        return MonteCarloReport(
            simulations=self.n_simulations,
            median_return_pct=float(np.median(sim_returns)),
            p5_return_pct=float(np.percentile(sim_returns, 5)),
            p95_return_pct=float(np.percentile(sim_returns, 95)),
            median_max_drawdown_pct=float(np.median(sim_drawdowns)),
            worst_case_drawdown_pct=float(np.percentile(sim_drawdowns, 99)),
            ruin_probability_pct=(ruined_count / self.n_simulations) * 100.0,
            median_sharpe=float(np.median(sim_sharpes)),
            p5_sharpe=float(np.percentile(sim_sharpes, 5)),
        )
