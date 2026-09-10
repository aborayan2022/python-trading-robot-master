# Python Trading Robot

## Production Safety Notice

The production path is Alpaca paper first. Use `PYROBOT_PROFILE=alpaca_paper`
for real Alpaca paper trading. Live trading is locked by default:
`PYROBOT_PROFILE=alpaca_live_locked` fails unless
`PYROBOT_ALLOW_LIVE_TRADING=true` is set explicitly after the paper-trading
acceptance gates are complete.

See `docs/production_runbook.md` for profiles, stop conditions, and daily
review procedures.

## Table of Contents

- [Overview](#overview)
- [Management Console — غرفة قيادة المدير](#management-console--غرفة-قيادة-المدير)
- [Runtime Trading Loop](#runtime-trading-loop)
- [What's New in v0.2.0](#whats-new-in-v020)
- [Setup](#setup)
- [Quickstart](#quickstart)
- [Supported Brokers](#supported-brokers)
- [Architecture](#architecture)
- [Backtesting](#backtesting)
- [Indicators](#indicators)

## Management Console — غرفة قيادة المدير

A single-process real-time web dashboard for telemetry, risk control, and lifecycle management:

```bash
# Launch the Management Console and trading loop (binds to http://127.0.0.1:8080)
python -m pyrobot.console
```

- **Interactive UI**: Real-time SSE streaming, Canvas equity curve, live positions/orders, and streaming signals.
- **Bilingual**: Instant toggle between Arabic (العربية) and English (LTR/RTL).
- **Role-Based Access Control (RBAC)**:
  - `manager` (`manager-token`): Full lifecycle, configuration, risk limits, kill switch, and live unlocking.
  - `dev` (`dev-token`): Telemetry, metrics, and tamper-evident cryptographic audit ledger.
  - `viewer` (`viewer-token`): Read-only overview and reporting.
- **Live Trading Safety Gate**: Multi-step unlock requiring manager role, `PYROBOT_ALLOW_LIVE_TRADING=true`, exact confirmation phrase, and audit tracking.

## Runtime Trading Loop

The full connected path — data → features/signals → risk gates → execution → tamper-evident audit — runs as one loop:

```bash
# Paper-mode replay demo (no broker account, no real money)
PYROBOT_SYMBOLS=MSFT,AAPL PYROBOT_BARS=500 PYROBOT_SIGNAL_SOURCE=example \
    python -m pyrobot.runtime.loop

# Or drive any registered strategy by name (Wave 5 wiring)
PYROBOT_STRATEGY=crypto_trend PYROBOT_SYMBOLS=BTC-USD PYROBOT_BARS=500 \
    python pyrobot/runtime/loop.py
```

The audit trail lands in `data/audit/ledger.jsonl` as a verifiable SHA-256 hash chain that survives restarts. `TradingPipeline` / `TradingLoop` (`pyrobot/runtime/`) are the integration points for live bar providers. See `IMPLEMENTATION_STATUS.md` for the roadmap state.

## Multi-Market (US / Metals / Crypto)

Three markets, seven strategies, bi-directional execution, honest next-bar-open
backtests with `ExecutionCostModel` (spread, slippage, commission, SEC fee,
participation caps, and per-bar short borrow/carry). Paper-only — no live path.

Environment (see `.env.example`):

| Variable | Purpose |
|---|---|
| `PYROBOT_MARKET` | `US` (default) \| `metals` \| `crypto` — `DataProviderRegistry` |
| `PYROBOT_STRATEGY` | Registered strategy name for the loop (`StrategyRegistry`) |
| `PYROBOT_UNIVERSE` | Symbol override for backtests / paper sessions |
| `PYROBOT_DATA_DIR` | Root containing `data/` (default `.`) |
| `PYROBOT_METALS_YEARS` / `PYROBOT_CRYPTO_YEARS` | History length (default 5) |

Full honest backtests (5y daily, benchmark-compared, Monte Carlo validated via
`scripts/strategy_validation.py`):

```bash
for b in backtest_us_breakout backtest_us_mean_reversion \
         backtest_metals_trend backtest_metals_momentum \
         backtest_crypto_trend backtest_crypto_mean_rev; do
    python $b.py
done
python scripts/multi_market_comparison.py
python scripts/strategy_validation.py
```

Daily paper sessions persist `PaperBroker` state (`data/paper_state/*.json`) and
synchronize strategy holding state across runs:

```bash
python metals_paper_session.py --now   # COMEX metals, latest daily candle
python crypto_paper_session.py --now   # crypto, 24/7/365
python metals_paper_session.py --dry-run   # full path, no orders
```

Results and the honest revalidated numbers are in
`reports/AI_Quant_Multi_Market_Advisory_Report.md`; market decisions live in
`reports/decision_memo_metals.md` and `reports/decision_memo_crypto.md`.

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
# Core only (paper trading + backtesting) — console tests are skipped
pip install -e .

# With a specific broker
pip install -e ".[alpaca]"
pip install -e ".[schwab]"
pip install -e ".[ibkr]"

# With management console
pip install -e ".[console]"

# Development (all extras + linting + type checking)
pip install -e ".[dev]"
```

### Test Suite

| Install command | What runs | Tests |
|---|---|---|
| `pip install -e .` | Core tests; console tests skipped when FastAPI is unavailable | See the current CI run |
| `pip install -e ".[console]"` or `pip install -e ".[dev]"` | Full suite including console tests | See the current CI run |

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
