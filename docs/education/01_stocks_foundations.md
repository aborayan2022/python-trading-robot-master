# Wave 0: US Stocks Foundations

**Market:** US Equities (NYSE / NASDAQ)
**Trading Hours:** 9:30–16:00 ET (pre-market 4:00–9:30, after-hours 16:00–20:00)
**Primary Data Source:** Alpaca (paper/live), yfinance (research/backtest)
**Settlement:** T+1

---

## Market Characteristics

US large-cap equities are the most liquid, most researched, and most regulated
securities in the world. They trade on centralized exchanges with transparent
order books, standardized reporting, and consistent corporate actions.

**Why US equities for our first market:**
- Deep liquidity → realistic execution simulation.
- Established broker infrastructure (Alpaca, Schwab, IBKR).
- Rich historical data (decades of daily OHLCV).
- Clear benchmarking universe (S&P 500, sector ETFs).

## Trading Costs

| Cost Component | Typical Range | Our Model |
|----------------|---------------|-----------|
| Spread | 0.01–0.05% | `ExecutionCostModel` spread component |
| Slippage | 0.02–0.10% | sqrt market impact model |
| Commission | $0 (most brokers) | $0 commission, SEC fee only |
| SEC Fee | ~$0.0000278/share | Modeled in `ExecutionCostModel` |
| Market Impact | Volume-dependent | Participation-capped model |

## Key Risks

1. **Earnings volatility** — overnight gaps around quarterly reports.
2. **Sector concentration** — portfolio may cluster in tech.
3. **Correlation risk** — "diversified" positions may move together in drawdowns.
4. **Regulatory changes** — SEC rule changes, short-sale restrictions.
5. **Liquidity traps** — small-caps may have poor execution in live.

## Why Trend Following Works Here

US equities exhibit long-term upward drift (equity risk premium). Trend-following
captures this drift while avoiding the worst drawdowns. The `USTrendFollowStrategy`
exploits this by:
- Buying above SMA(200) — confirming the long-term uptrend.
- Using EMA(21) > EMA(50) — intermediate momentum confirmation.
- RSI(14) band filter — avoiding overbought entries.
- ATR% filter — avoiding high-volatility environments.

## Data Storage

```text
data/us_market/
├── AAPL.csv
├── MSFT.csv
├── ... (10 symbols)
```

Cached daily OHLCV from yfinance. Used by `us_strategy_backtest.py`.

## Benchmark

Buy & Hold equal-weight portfolio of the same universe, with the same
`ExecutionCostModel`. The strategy must beat this to justify its existence.

---

## Relation to Platform Code

| Component | File | Role |
|-----------|------|------|
| Data Provider | `pyrobot/data/alpaca.py` | Real-time + historical via Alpaca API |
| Strategy | `pyrobot/strategies/us_trend.py` | `USTrendFollowStrategy` |
| Backtest | `us_strategy_backtest.py` | Honest cost-adjusted backtest |
| Paper Session | `us_paper_session.py` | Daily paper trading |
| Quality Check | `pyrobot/data/quality.py` | `DataQualityEngine` |
