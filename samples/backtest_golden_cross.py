"""Sample: Backtest the Golden Crossover strategy."""

import operator

from datetime import datetime
from datetime import timedelta

from pyrobot.indicators import Indicators
from pyrobot.backtesting.engine import BacktestEngine


def generate_historical_data():
    """Generate synthetic price data for backtesting."""
    import numpy as np

    np.random.seed(42)
    bars = []
    base_price = 400.0

    for i in range(500):
        ts = int(
            (datetime(2023, 1, 2) + timedelta(days=i)).timestamp() * 1000
        )
        change = np.random.uniform(-5, 5)
        open_p = base_price + change
        close_p = open_p + np.random.uniform(-3, 3)
        high_p = max(open_p, close_p) + np.random.uniform(0, 3)
        low_p = min(open_p, close_p) - np.random.uniform(0, 3)
        volume = int(np.random.uniform(50000, 500000))

        bars.append(
            {
                "symbol": "MSFT",
                "open": round(open_p, 2),
                "close": round(close_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "volume": volume,
                "datetime": ts,
            }
        )
        base_price = close_p

    return bars


def golden_cross_strategy(stock_frame, indicator_client):
    """Golden Crossover: Buy when SMA(50) crosses above SMA(200), sell when it crosses below."""
    frame = stock_frame.frame

    if "sma_50" not in frame.columns or "sma_200" not in frame.columns:
        return None

    try:
        latest = frame.xs("MSFT", level=0).iloc[-1]
        prev = frame.xs("MSFT", level=0).iloc[-2]
    except (IndexError, KeyError):
        return None

    sma_50_now = latest.get("sma_50")
    sma_200_now = latest.get("sma_200")
    sma_50_prev = prev.get("sma_50")
    sma_200_prev = prev.get("sma_200")

    if any(pd.isna([sma_50_now, sma_200_now, sma_50_prev, sma_200_prev])):
        return None

    if sma_50_prev <= sma_200_prev and sma_50_now > sma_200_now:
        return "buy"

    if sma_50_prev >= sma_200_prev and sma_50_now < sma_200_now:
        return "sell"

    return None


def setup_indicators(indicator_client):
    """Configure the indicators for the Golden Crossover strategy."""
    indicator_client.sma(period=50, column_name="sma_50")
    indicator_client.sma(period=200, column_name="sma_200")


if __name__ == "__main__":
    import pandas as pd

    historical_data = generate_historical_data()

    engine = BacktestEngine(
        initial_balance=100_000.0,
        historical_data=historical_data,
        commission_per_trade=1.0,
        slippage_pct=0.001,
    )

    result = engine.run(
        strategy=golden_cross_strategy,
        indicator_setup=setup_indicators,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
    )

    print("=" * 60)
    print("BACKTEST RESULTS: Golden Crossover (SMA 50/200)")
    print("=" * 60)
    print(result)
    print()
    for key, value in result.summary().items():
        print(f"  {key}: {value}")
    print("=" * 60)
