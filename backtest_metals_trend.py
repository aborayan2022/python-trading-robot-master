"""Metals Trend backtest — MetalsTrendFollowStrategy against cached metals daily data.

Uses the shared ``MultiMarketBacktest`` runner for honest cost-adjusted
backtesting with next-bar-open fills, ExecutionCostModel, and a Buy & Hold
benchmark comparison.

Modes:
    --dry-run     cache-only validation (no network download)
    --refresh     force re-download from yfinance
    (default)     load cached data or download via yfinance (5-year daily)

Environment:
    PYROBOT_DATA_DIR    root for data/ (default ".")
    PYROBOT_METALS_YEARS  years of daily data (default 5)

Run:  .venv/bin/python backtest_metals_trend.py --dry-run
      .venv/bin/python backtest_metals_trend.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pyrobot.backtesting.cost_model import ExecutionCostModel
from pyrobot.backtesting.runner import MultiMarketBacktest
from pyrobot.data.metals_provider import DEFAULT_METALS
from pyrobot.strategies.metals_trend import MetalsTrendFollowStrategy

ROOT = Path(os.environ.get("PYROBOT_DATA_DIR", ".")).resolve()


def main() -> None:
    years = int(os.environ.get("PYROBOT_METALS_YEARS", "5"))
    refresh = "--refresh" in sys.argv
    dry_run = "--dry-run" in sys.argv
    symbols = [s.strip().upper() for s in os.environ.get("PYROBOT_UNIVERSE", ",".join(DEFAULT_METALS)).split(",") if s.strip()]

    cost_model = ExecutionCostModel()
    runner = MultiMarketBacktest(
        strategy_class=MetalsTrendFollowStrategy,
        strategy_name="metals_trend",
        symbols=symbols,
        data_dir=ROOT / "data" / "metals",
        initial_balance=100_000.0,
        years=years,
        cost_model=cost_model,
    )

    if dry_run:
        runner.dry_run()
    else:
        runner.run_all(refresh=refresh)


if __name__ == "__main__":
    main()
