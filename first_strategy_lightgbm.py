"""LightGBM strategy — 5 years, 10 large-cap US symbols (comparison to Logistic).

Per the consultant's directive (31 Aug 2026), the Logistic model (v2.0) achieved
OOS accuracy 51.65% vs buy-and-hold 56.91%. The governance system correctly
rejected it as CANDIDATE. This script runs the identical universe with LightGBM
to compare performance under the same governance framework.

Universe: 10 large-cap US equities across sectors.
Period:   5 years daily.
"""

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from pyrobot.ai.registry import ModelRegistry
from pyrobot.ai.training import (
    OptionalLightGBMDirectionModel,
    TrainingGateConfig,
    train_direction_champion_candidate,
)

SYMBOLS = [
    "AAPL",   # Technology
    "MSFT",   # Technology
    "NVDA",   # Technology / Semiconductors
    "AMZN",   # Consumer / Cloud
    "GOOGL",  # Technology / Advertising
    "META",   # Social media
    "JPM",    # Financials
    "XOM",    # Energy
    "JNJ",    # Healthcare
    "WMT",    # Consumer staples
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
    print("PyRobot — LightGBM Strategy (5y, 10 symbols)")
    print("=" * 70)

    print(f"\n1. Fetching daily data for {len(SYMBOLS)} symbols (5 years)...")
    market_data = fetch_real_data(SYMBOLS, period="5y")
    print(f"   Total rows: {len(market_data)}")
    print(f"   Date range: {market_data.index.min().date()} to {market_data.index.max().date()}")
    print(f"   Symbols: {sorted(market_data['symbol'].unique())}")

    print("\n2. Training LightGBM direction model via walk-forward validation...")
    registry_dir = Path("./first_strategy_lightgbm_models")
    registry_dir.mkdir(exist_ok=True)
    registry = ModelRegistry(registry_dir=registry_dir)

    gate = TrainingGateConfig(
        min_oos_accuracy_edge=0.01,
        min_oos_samples=200,
        max_calibration_error=0.20,
        min_oos_net_pnl=0.0,
        min_oos_trades=20,
        min_ev_per_trade=0.0,
        min_profit_factor=0.8,
    )

    report = train_direction_champion_candidate(
        market_data=market_data,
        registry=registry,
        model_id="us_direction_lgbm",
        version="v1.0",
        feature_engine=None,
        model_factory=lambda: OptionalLightGBMDirectionModel(
            model_id="us_direction_lgbm",
            version="v1.0",
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
        ),
        horizon=5,
        threshold=0.0,
        gate=gate,
        report_path="./first_strategy_lightgbm_report.json",
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
    print(f"   Report saved to: first_strategy_lightgbm_report.json")
    print(f"   Registry at: {registry_dir}")

    # Comparison summary
    print("\n" + "=" * 70)
    print("COMPARISON: Logistic v2.0 vs LightGBM v1.0")
    print("=" * 70)
    try:
        logistic_report = json.loads(
            Path("./first_strategy_expanded_report.json").read_text(encoding="utf-8")
        )
        lgbm_oos = report["baselines"]["buy_and_hold"]
        log_oos = logistic_report.get("baselines", {}).get("buy_and_hold", "N/A")
        print(f"  Buy & Hold baseline: {lgbm_oos:.4f}")
        print(f"  Logistic OOS accuracy: {logistic_report['model']['oos_metrics']['oos_accuracy']:.4f}")
        print(f"  LightGBM OOS accuracy: {report['model']['oos_metrics']['oos_accuracy']:.4f}")
        print(f"  Logistic trades: {logistic_report['model']['oos_metrics']['n_trades']}")
        print(f"  LightGBM trades: {report['model']['oos_metrics']['n_trades']}")
        print(f"  Logistic approved: {logistic_report['approved_for_challenger']}")
        print(f"  LightGBM approved: {report['approved_for_challenger']}")
    except FileNotFoundError:
        print("  (Logistic report not found for comparison)")


if __name__ == "__main__":
    main()
