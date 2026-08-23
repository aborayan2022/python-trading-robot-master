"""Shared test fixtures for the pyrobot test suite."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.stock_frame import StockFrame


@pytest.fixture
def paper_broker():
    """An authenticated PaperBroker with $100k balance."""
    broker = PaperBroker(initial_balance=100_000.0)
    broker.authenticate()
    return broker


@pytest.fixture
def sample_bars():
    """Generate 100 sample minute bars for MSFT."""
    np.random.seed(42)
    base_price = 400.0
    bars = []
    start_dt = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)

    for i in range(100):
        ts = int((start_dt + timedelta(minutes=i)).timestamp() * 1000)
        change = np.random.uniform(-2, 2)
        open_p = base_price + change
        close_p = open_p + np.random.uniform(-1, 1)
        high_p = max(open_p, close_p) + np.random.uniform(0, 1)
        low_p = min(open_p, close_p) - np.random.uniform(0, 1)
        volume = int(np.random.uniform(10000, 100000))

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


@pytest.fixture
def sample_bars_multi_symbol():
    """Generate sample bars for MSFT and AAPL."""
    np.random.seed(42)
    bars = []
    start_dt = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)

    for symbol, base_price in [("MSFT", 400.0), ("AAPL", 180.0)]:
        price = base_price
        for i in range(50):
            ts = int((start_dt + timedelta(minutes=i)).timestamp() * 1000)
            change = np.random.uniform(-2, 2)
            open_p = price + change
            close_p = open_p + np.random.uniform(-1, 1)
            high_p = max(open_p, close_p) + np.random.uniform(0, 1)
            low_p = min(open_p, close_p) - np.random.uniform(0, 1)
            volume = int(np.random.uniform(10000, 100000))

            bars.append(
                {
                    "symbol": symbol,
                    "open": round(open_p, 2),
                    "close": round(close_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "volume": volume,
                    "datetime": ts,
                }
            )
            price = close_p

    return bars


@pytest.fixture
def stock_frame(sample_bars):
    """A StockFrame populated with sample bars."""
    return StockFrame(data=sample_bars)


@pytest.fixture
def stock_frame_multi(sample_bars_multi_symbol):
    """A StockFrame with multiple symbols."""
    return StockFrame(data=sample_bars_multi_symbol)


@pytest.fixture
def market_order():
    """A sample market order dict."""
    return {
        "orderType": "MARKET",
        "session": "NORMAL",
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": 10,
                "instrument": {
                    "symbol": "MSFT",
                    "assetType": "EQUITY",
                },
            }
        ],
    }


@pytest.fixture
def limit_order():
    """A sample limit order dict."""
    return {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "duration": "DAY",
        "price": 395.00,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": 10,
                "instrument": {
                    "symbol": "MSFT",
                    "assetType": "EQUITY",
                },
            }
        ],
    }
