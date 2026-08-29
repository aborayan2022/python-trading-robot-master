"""First real US market data training run — AAPL + MSFT daily direction model.

This script:
1. Fetches 2 years of daily AAPL + MSFT data via yfinance (no API key needed)
2. Trains a direction classifier via walk-forward validation
3. Evaluates OOS accuracy, calibration, and economic performance
4. Registers the model in the local registry with full governance
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from pyrobot.ai.registry import ModelRegistry
from pyrobot.ai.training import (
    TrainingGateConfig,
    train_direction_champion_candidate,
)


def fetch_real_data(symbols: list[str], period: str = "2y") -> pd.DataFrame:
    """Fetch daily OHLCV data from Yahoo Finance."""
    frames = []
    for sym in symbols:
        raw = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=True)
        if raw.empty:
            print(f"Warning: no data for {sym}, skipping")
            continue
        df = pd.DataFrame({
            "open": raw["Open"],
            "high": raw["High"],
            "low": raw["Low"],
            "close": raw["Close"],
            "volume": raw["Volume"],
        })
        df.index = pd.to_datetime(df.index, utc=True)
        df.index.name = "datetime"
        df["symbol"] = sym
        frames.append(df)
        print(f"Fetched {sym}: {len(df)} daily bars from {df.index[0].date()} to {df.index[-1].date()}")

    if not frames:
        raise ValueError("No data fetched for any symbol")

    return pd.concat(frames).sort_index()


def main():
    print("=" * 70)
    print("PyRobot — First Real US Market Data Training Run")
    print("=" * 70)

    # Fetch data
    symbols = ["AAPL", "MSFT"]
    print(f"\n1. Fetching daily data for {symbols} (2 years)...")
    market_data = fetch_real_data(symbols, period="2y")
    print(f"   Total rows: {len(market_data)}")
    print(f"   Date range: {market_data.index[0].date()} to {market_data.index[-1].date()}")

    # Train
    print("\n2. Training direction model via walk-forward validation...")
    registry_dir = Path("./first_strategy_models")
    registry_dir.mkdir(exist_ok=True)
    registry = ModelRegistry(registry_dir=registry_dir)

    gate = TrainingGateConfig(
        min_oos_accuracy_edge=0.01,
        min_oos_samples=50,
        max_calibration_error=0.20,
        min_oos_net_pnl=0.0,
        min_oos_trades=5,
        min_ev_per_trade=0.0,
        min_profit_factor=0.8,
    )

    report = train_direction_champion_candidate(
        market_data=market_data,
        registry=registry,
        model_id="us_direction_v1",
        version="v1.0",
        horizon=5,
        threshold=0.0,
        gate=gate,
        report_path="./first_strategy_report.json",
        n_splits=3,
        train_period_days=50,
        test_period_days=15,
        embargo_days=2,
    )

    # Display results
    print("\n3. Results:")
    print(f"   Approved for challenger: {report['approved_for_challenger']}")
    print(f"   Walk-forward summary:")
    wf = report["walk_forward"]
    for key in ["oos_accuracy", "train_accuracy", "oos_predictions"]:
        if key in wf:
            print(f"     {key}: {wf[key]}")

    print(f"   Baselines:")
    for k, v in report["baselines"].items():
        print(f"     {k}: {v:.4f}")

    print(f"   Calibration (OOS):")
    ece = report["calibration_oos"].get("expected_calibration_error", "N/A")
    print(f"     ECE: {ece}")

    meta = report["model"]
    oos_m = meta.get("oos_metrics", {})
    print(f"   Economic metrics:")
    for k in ["net_pnl_after_costs", "sharpe", "profit_factor", "n_trades", "ev_per_trade"]:
        if k in oos_m:
            print(f"     {k}: {oos_m[k]}")

    shadow_keys = ["shadow_accuracy", "shadow_ece", "shadow_net_pnl"]
    has_shadow = any(k in oos_m for k in shadow_keys)
    if has_shadow:
        print(f"   Shadow metrics:")
        for k in shadow_keys:
            if k in oos_m:
                print(f"     {k}: {oos_m[k]}")

    print(f"\n   Model status: {meta.get('status')}")
    print(f"   Report saved to: first_strategy_report.json")
    print(f"   Registry at: {registry_dir}")

    # Save report
    with open("first_strategy_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n4. Done. Report written to first_strategy_report.json")


if __name__ == "__main__":
    main()
