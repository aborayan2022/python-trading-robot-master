"""Quantitative Backtesting and Research Validation Package."""

from pyrobot.backtesting.engine import BacktestEngine, BacktestResult
from pyrobot.backtesting.cost_model import ExecutionCostModel, CostModelConfig
from pyrobot.backtesting.metrics import calculate_quantitative_metrics, QuantitativeReport
from pyrobot.backtesting.walk_forward import WalkForwardValidator, WalkForwardSplit
from pyrobot.backtesting.monte_carlo import MonteCarloSimulator, MonteCarloReport

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "ExecutionCostModel",
    "CostModelConfig",
    "calculate_quantitative_metrics",
    "QuantitativeReport",
    "WalkForwardValidator",
    "WalkForwardSplit",
    "MonteCarloSimulator",
    "MonteCarloReport",
]
