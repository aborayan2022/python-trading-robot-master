# Wave 0: Metals Foundations

**Market:** Precious Metals (Gold, Silver, Platinum, Palladium)
**Trading Hours:** COMEX: 9:00–14:30 ET (electronic: nearly 23h via Globex)
**Primary Data Source:** yfinance (GC=F, SI=F, GLD, SLV)
**Settlement:** Varies by instrument

---

## Market Characteristics

Precious metals are commodity assets that trade on exchanges like COMEX
(Commodity Exchange, part of CME Group). Unlike equities, metals have no
earnings, no dividends, and no corporate governance — their price is driven
by supply/demand, macroeconomic conditions, currency strength (especially USD),
and geopolitical risk.

**Key metals and their tickers:**

| Metal | Futures Ticker | ETF Ticker | Character |
|-------|---------------|------------|-----------|
| Gold | `GC=F` | `GLD` | Safe haven, inflation hedge, dollar inverse |
| Silver | `SI=F` | `SLV` | Industrial + monetary, higher volatility |
| Platinum | `PL=F` | — | Industrial (autocatalysts), supply-constrained |
| Palladium | `PA=F` | — | Industrial (catalytic converters), supply shocks |

## How Metals Differ from Stocks

| Dimension | Stocks | Metals |
|-----------|--------|--------|
| Value driver | Earnings, growth | Supply/demand, macro |
| Trading hours | 6.5h/day | ~23h/day (Globex) |
| Volatility | Moderate | Higher (especially silver) |
| Trend persistence | Long secular trends | Regime-dependent (safe haven vs. risk-on) |
| Correlation | Sector-dependent | Inverse USD, inflation-linked |
| Cost structure | Commission-free | Futures: exchange fees, roll costs |

## Trading Costs

| Cost Component | Typical Range | Notes |
|----------------|---------------|-------|
| Spread (futures) | 0.01–0.05% | Tighter for gold, wider for palladium |
| Slippage | 0.02–0.10% | Depends on contract volume |
| Roll cost | 0.1–0.5% per roll | When futures contracts expire |
| ETF spread | 0.01–0.03% | GLD/SLV have tight spreads |
| Commission | Broker-dependent | Not modeled in our paper backtest |

## Key Risks

1. **Dollar strength** — metals are priced in USD; strong dollar = weak metals.
2. **Interest rates** — higher rates increase opportunity cost of holding non-yielding assets.
3. **Contango/backwardation** — futures curve shape affects returns.
4. **Liquidity** — thin markets (platinum, palladium) can gap.
5. **Regulatory** — position limits, margin changes by CME.
6. **Geopolitical** — safe-haven spikes can reverse quickly.

## Why Trend Following Works Here

Gold and silver exhibit strong trending behavior during macro regimes:
- Inflation fears → gold rally (2020-2022).
- Rate cuts → metals breakout.
- Geopolitical crisis → safe-haven demand.

`MetalsTrendFollowStrategy` captures these regime-driven trends.

## Why Momentum Breakout Works Here

Metals often consolidate in ranges before explosive breakouts:
- Silver's breakout from $20 to $30 (2020).
- Gold's breakout above $2000 (multiple times).

`MetalsMomentumBreakout` catches these with volume confirmation.

## Data Storage

```text
data/metals/
├── GC=F.csv      # Gold Futures
├── SI=F.csv      # Silver Futures
├── GLD.csv       # Gold ETF
├── SLV.csv       # Silver ETF
```

## Benchmark

Buy & Hold of the same metal (e.g., long gold futures or GLD ETF).
The strategy must outperform with better risk-adjusted returns.

---

## Relation to Platform Code

| Component | File | Role |
|-----------|------|------|
| Data Provider | `pyrobot/data/metals_provider.py` | yfinance-based metals data |
| Strategy (trend) | `pyrobot/strategies/metals_trend.py` | `MetalsTrendFollowStrategy` |
| Strategy (momentum) | `pyrobot/strategies/metals_momentum.py` | `MetalsMomentumBreakout` |
| Backtest | `backtest_metals_trend.py` | Cost-adjusted backtest |
| Paper Session | `metals_paper_session.py` | Paper trading |
