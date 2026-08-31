"""Expanded first strategy — 5 years, 10 large-cap US symbols.

Per the consultant's directive (final report, 30 Aug 2026), the original first
strategy (AAPL+MSFT, 2y) produced only n_trades=1, which is not statistically
meaningful. This run widens the data range (more tokens and more years) so the
governance pipeline can evaluate a statistically meaningful number of trades
(minimum ~20) before any model can be approved.

Universe: 10 large-cap US equities across sectors.
Period:   5 years daily.
"""

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from pyrobot.ai.registry import ModelRegistry
from pyrobot.ai.training import (
    TrainingGateConfig,
    train_direction_champion_candidate,
)

SYMBOLS = [
    "AAPL",  # Technology
    "MSFT",  # Technology
    "NVDA",  # Technology / Semiconductors
    "AMZN",  # Consumer / Cloud
    "GOOGL",  # Technology / Advertising
    "META",  # Social media
    "JPM",  # Financials
    "XOM",  # Energy
    "JNJ",  # Healthcare
    "WMT",  # Consumer staples
]


def fetch_real_data(symbols: list[str], period: str = "5y") -> pd.DataFrame:
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
    print("PyRobot — Expanded First Strategy (5y, 10 symbols)")
    print("=" * 70)

    print(f"\n1. Fetching daily data for {len(SYMBOLS)} symbols (5 years)...")
    market_data = fetch_real_data(SYMBOLS, period="5y")
    print(f"   Total rows: {len(market_data)}")
    print(f"   Date range: {market_data.index.min().date()} to {market_data.index.max().date()}")
    print(f"   Symbols: {sorted(market_data['symbol'].unique())}")

    print("\n2. Training direction model via walk-forward validation...")
    registry_dir = Path("./first_strategy_models")
    registry_dir.mkdir(exist_ok=True)
    registry = ModelRegistry(registry_dir=registry_dir)

    gate = TrainingGateConfig(
        min_oos_accuracy_edge=0.01,
        min_oos_samples=200,
        max_calibration_error=0.20,
        min_oos_net_pnl=0.0,
        min_oos_trades=20,   # consultant's statistical-significance floor
        min_ev_per_trade=0.0,
        min_profit_factor=0.8,
    )

    report = train_direction_champion_candidate(
        market_data=market_data,
        registry=registry,
        model_id="us_direction_v2",
        version="v2.0",
        horizon=5,
        threshold=0.0,
        gate=gate,
        report_path="./first_strategy_expanded_report.json",
        n_splits=4,
        train_period_days=252,
        test_period_days=63,
        embargo_days=5,
    )

    print("\n3. Results:")
    print(f"   Approved for challenger: {report['approved_for_challenger']}")

    wf = report["walk_forward"]
    print("   Walk-forward summary:")
    print(f"     n_folds: {wf.get('n_folds')}")
    print(f"     fold_scores: {wf.get('fold_scores')}")
    print(f"     oos_score: {wf.get('oos_score'):.4f}")
    print(f"     n_oos_predictions: {wf.get('n_oos_predictions')}")

    print("   Baselines:")
    for k, v in report["baselines"].items():
        print(f"     {k}: {v:.4f}")

    meta = report["model"]
    oos_m = meta.get("oos_metrics", {})
    print("   Economic metrics (OOS):")
    for k in ["oos_accuracy", "net_pnl_after_costs", "sharpe", "profit_factor",
              "n_trades", "ev_per_trade", "max_drawdown"]:
        if k in oos_m:
            print(f"     {k}: {oos_m[k]}")

    shadow_keys = ["shadow_accuracy", "shadow_ece", "shadow_net_pnl", "shadow_n_trades"]
    if any(k in oos_m for k in shadow_keys):
        print("   Shadow metrics:")
        for k in shadow_keys:
            if k in oos_m:
                print(f"     {k}: {oos_m[k]}")

    print(f"\n   Model status: {meta.get('status')}")
    print(f"   Report saved to: first_strategy_expanded_report.json")
    print(f"   Registry at: {registry_dir}")


if __name__ == "__main__":
    main()
