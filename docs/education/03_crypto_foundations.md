# Wave 0: Crypto Foundations

**Market:** Digital Assets (Bitcoin, Ethereum, Solana, Binance Coin)
**Trading Hours:** 24/7/365 (no market close, no holidays)
**Primary Data Source:** yfinance (BTC-USD, ETH-USD), CCXT (future)
**Settlement:** T+0 (instant on-chain), T+1 on exchanges

---

## Market Characteristics

Cryptocurrency markets operate continuously with no centralized closing bell.
Prices are driven by adoption metrics, network activity, regulatory news,
macro sentiment, and speculative flows. The market is younger, less regulated,
and more volatile than traditional assets.

**Key assets:**

| Asset | Ticker | Market Cap Rank | Character |
|-------|--------|----------------|-----------|
| Bitcoin | `BTC-USD` | #1 | Digital gold, store of value, macro asset |
| Ethereum | `ETH-USD` | #2 | Smart contracts, DeFi, utility token |
| Solana | `SOL-USD` | Top 5 | High-throughput L1, meme coins |
| Binance Coin | `BNB-USD` | Top 5 | Exchange token, BSC ecosystem |

## How Crypto Differs from Stocks and Metals

| Dimension | Stocks | Metals | Crypto |
|-----------|--------|--------|--------|
| Trading hours | 6.5h/day | ~23h/day | 24/7/365 |
| Regulation | SEC, FINRA | CME, CFTC | Fragmented, evolving |
| Volatility | Moderate | Moderate-High | Very High (2-5x stocks) |
| Trend persistence | Strong | Regime-dependent | Strong but violent reversals |
| Data availability | Decades | Decades | ~10 years (BTC since 2010) |
| Market maturity | >100 years | >50 years | ~15 years |
| Correlation to equities | Sector-dependent | Low-moderate | Increasing (risk-on asset) |

## Trading Costs

| Cost Component | Typical Range | Notes |
|----------------|---------------|-------|
| Spread | 0.01–0.10% | Varies by pair and venue |
| Slippage | 0.05–0.50% | Higher in volatile periods |
| Taker fee | 0.04–0.10% | Binance, Coinbase tier-1 |
| Maker fee | 0.00–0.06% | Liquidity provider rebates |
| Network fee | Variable | On-chain transfers (not for spot trading) |
| Funding rate | 0.01% / 8h | Perpetual swaps (not spot) |

## Key Risks

1. **Extreme volatility** — 10-30% daily moves are not uncommon.
2. **Exchange risk** — counterparty risk (FTX collapse, 2022).
3. **Regulatory uncertainty** — SEC enforcement, global bans.
4. **Flash crashes** — thin liquidity + leverage = cascading liquidations.
5. **Smart contract risk** — DeFi exploits, bridge hacks.
6. **Correlation spikes** — all crypto sells off together in risk-off events.
7. **24/7 execution** — no circuit breakers, no after-hours protection.

## Why Trend Following Works Here

Crypto exhibits strong momentum regimes:
- Bitcoin bull runs (2017, 2020-2021) show persistent trends.
- Altcoin seasons follow BTC breakouts.
- Bear markets (2018, 2022) show persistent downtrends.

`CryptoTrendBreakoutStrategy` captures these with volatility-adaptive stops.

## Why Mean Reversion Works Here

Crypto's high volatility creates frequent overextensions:
- RSI reaching extreme levels (<20 or >80) often reverses.
- Bollinger Band stretches tend to revert.
- Funding rate extremes signal crowd positioning.

`CryptoMeanReversionStrategy` exploits these with strict risk controls.

## Data Storage

```text
data/crypto/
├── BTC-USD.csv
├── ETH-USD.csv
```

## Benchmark

Buy & Hold Bitcoin (or the same asset). Given crypto's high volatility,
the strategy must demonstrate superior risk-adjusted returns (Sharpe, Sortino)
to justify active management.

---

## Relation to Platform Code

| Component | File | Role |
|-----------|------|------|
| Data Provider | `pyrobot/data/crypto_provider.py` | yfinance-based crypto data |
| Strategy (trend) | `pyrobot/strategies/crypto_trend.py` | `CryptoTrendBreakoutStrategy` |
| Strategy (mean rev) | `pyrobot/strategies/crypto_mean_rev.py` | `CryptoMeanReversionStrategy` |
| Backtest | `backtest_crypto_trend.py` | Cost-adjusted backtest |
| Paper Session | `crypto_paper_session.py` | Paper trading (24/7) |
