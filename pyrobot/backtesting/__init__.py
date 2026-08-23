"""Quantitative Backtesting and Research Validation Package."""

from pyrobot.backtesting.cost_model import CostModelConfig, ExecutionCostModel
from pyrobot.backtesting.engine import BacktestEngine, BacktestResult
from pyrobot.backtesting.metrics import QuantitativeReport, calculate_quantitative_metrics
from pyrobot.backtesting.monte_carlo import MonteCarloReport, MonteCarloSimulator
from pyrobot.backtesting.walk_forward import (
    WalkForwardResult,
    WalkForwardSplit,
    WalkForwardValidator,
    run_walk_forward,
)

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "ExecutionCostModel",
    "CostModelConfig",
    "calculate_quantitative_metrics",
    "QuantitativeReport",
    "WalkForwardValidator",
    "WalkForwardSplit",
    "WalkForwardResult",
    "run_walk_forward",
    "MonteCarloSimulator",
    "MonteCarloReport",
]
