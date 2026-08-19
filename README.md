# Python Trading Robot

## Table of Contents

- [Overview](#overview)
- [What's New in v0.2.0](#whats-new-in-v020)
- [Setup](#setup)
- [Quickstart](#quickstart)
- [Supported Brokers](#supported-brokers)
- [Architecture](#architecture)
- [Backtesting](#backtesting)
- [Indicators](#indicators)

## Overview

A trading robot written in Python that can run automated strategies using technical analysis. The robot supports multiple brokers through a unified abstraction layer.

**Core objects:**

- **Portfolio** — Tracks positions, calculates risk metrics (variance, allocation, Sharpe), and projects market values in real-time.
- **Trade** — Defines orders (market, limit, stop, bracket) with legs, stop losses, and take profits.
- **StockFrame** — Real-time multi-index DataFrame storing historical and live OHLCV data.
- **Indicators** — Calculates technical indicators (RSI, Bollinger Bands, Stochastic, CCI, KST, ADX, VWAP, Ichimoku Cloud, OBV, and more).

## What's New in v0.2.0

- **Broker abstraction layer** — Switch brokers by changing one line of code
- **Paper trading simulator** — Test strategies with no broker account
- **Backtesting engine** — Run strategies against historical data with Sharpe, Sortino, max drawdown metrics
- **Custom exception hierarchy** — `BrokerError`, `AuthenticationError`, `OrderRejectedError`, etc.
- **Centralized logging** — Replace all `print()` with proper Python logging
- **Bug fixes** — Bollinger Bands, Stochastic Oscillator, CCI, KST, signal execution logic
- **Modern Python** — `pyproject.toml`, Python >=3.10, type hints throughout

## Setup

```bash
# Core only (paper trading + backtesting)
pip install -e .

# With a specific broker
pip install -e ".[alpaca]"
pip install -e ".[schwab]"
pip install -e ".[ibkr]"

# Development
pip install -e ".[dev]"
```

## Quickstart

### Paper Trading (No Broker Account)

```python
from pyrobot.brokers import create_broker
from pyrobot.robot import PyRobot

broker = create_broker('paper')
broker.authenticate()

robot = PyRobot(broker=broker)
robot.create_portfolio()

# Add positions
robot.portfolio.add_position(symbol='MSFT', quantity=10, asset_type='equity')

# Create a trade
trade = robot.create_trade(
    trade_id='long_msft',
    enter_or_exit='enter',
    long_or_short='long',
    order_type='mkt'
)
trade.instrument(symbol='MSFT', quantity=5, asset_type='EQUITY')
```

### Live Trading (Alpaca Example)

```python
from pyrobot.brokers import create_broker

broker = create_broker(
    'alpaca',
    api_key='YOUR_API_KEY',
    secret_key='YOUR_SECRET_KEY',
    paper=True  # Set False for live
)
broker.authenticate()

quotes = broker.get_quotes(['MSFT', 'AAPL'])
print(quotes)
```

### Live Trading (Schwab Example)

```python
from pyrobot.brokers import create_broker

broker = create_broker(
    'schwab',
    client_id='YOUR_CLIENT_ID',
    redirect_uri='https://localhost/callback',
    credentials_path='path/to/tokens.json'
)
broker.authenticate()
```

## Supported Brokers

| Broker | Package | Auth Method | Paper Trading |
|--------|---------|-------------|---------------|
| Paper | (built-in) | None needed | Built-in simulator |
| Alpaca | `alpaca-py` | API key + secret | Yes |
| Schwab | `schwab-py` | OAuth 2.0 | No |
| IBKR | `ib_insync` | TWS/Gateway | No |

## Architecture

```
pyrobot/
├── brokers/
│   ├── base.py              # BrokerInterface ABC
│   ├── paper_broker.py      # Local simulator
│   ├── alpaca_broker.py     # Alpaca adapter
│   ├── schwab_broker.py     # Charles Schwab adapter
│   └── ibkr_broker.py       # Interactive Brokers adapter
├── backtesting/
│   └── engine.py            # BacktestEngine + BacktestResult
├── robot.py                 # Main PyRobot class
├── indicators.py            # Technical indicators
├── stock_frame.py           # Multi-index price DataFrame
├── trades.py                # Trade/order management
├── portfolio.py             # Portfolio tracking
├── exceptions.py            # Custom exceptions
└── logging_config.py        # Centralized logging
```

## Backtesting

```python
from pyrobot.backtesting.engine import BacktestEngine

engine = BacktestEngine(
    initial_balance=100_000,
    historical_data=your_price_data,  # List of dicts with symbol,open,close,high,low,volume,datetime
    commission_per_trade=1.0,
    slippage_pct=0.001,
)

def golden_cross(stock_frame, indicator_client):
    """Buy when 50-SMA crosses above 200-SMA."""
    # ... indicator logic ...
    return "buy"  # or "sell" or None

result = engine.run(strategy=golden_cross)
print(result.summary())
# {'total_return_pct': 5.23, 'sharpe_ratio': 1.45, 'max_drawdown_pct': -3.21, ...}
```

## Indicators

```python
from pyrobot.indicators import Indicators

indicators = Indicators(price_data_frame=stock_frame)

indicators.rsi(period=14)
indicators.bollinger_bands(period=20)
indicators.stochastic_oscillator()
indicators.sma(period=200)
indicators.ema(period=50)
indicators.adx()
indicators.vwap()
indicators.obv()
indicators.ichimoku_cloud()
indicators.cci()
indicators.kst()
```
