# Decision Memo: Cryptocurrency

**Date:** 2026-09-10 (post-hoc — see §10)
**Requested by:** Programmer Team Leader (Wave 1 — Multi-Market expansion)
**Market:** Crypto (BTC-USD, ETH-USD)

## 1. Why this market?
- Crypto is one of the directive's three expansion targets and the only
  24/7/365 market, providing differentiation from the 23h metals window and the
  US cash-session window.
- BTC and ETH have liquid, quotable daily series (yfinance back to 2014/2016),
  making honest daily-bar backtests and paper sessions feasible now, with CCXT
  reserved for intraday later.

## 2. Data Source
- yfinance tickers: `BTC-USD` (Bitcoin), `ETH-USD` (Ethereum).
- Cached to `data/crypto/*.csv` (5-year daily OHLCV, UTC).
- Reference: exchange market-structure documentation; CCXT for exchange
  connectivity (deferred).

## 3. Trading Calendar
- Crypto trades 24/7/365 — no market close, no holidays.
- `CryptoProvider.TRADING_CALENDAR` models a daily 365-day calendar; the two
  crypto backtest scripts annualize with `periods_per_year=365`.

## 4. Expected Strategies
- `CryptoTrendBreakoutStrategy` (`crypto_trend.py`) — trend/breakout, LONG+SHORT.
- `CryptoMeanReversionStrategy` (`crypto_mean_rev.py`) — mean reversion,
  LONG+SHORT, with enforced stop-loss.

## 5. Benchmark
- Equal-weight Buy & Hold over BTC-USD and ETH-USD, cost-adjusted
  (`runner.buy_and_hold_benchmark`), each symbol entered at its own first bar.
- Reference window 2021-09 → 2026-09 returns **+18.0%** — the bar crypto
  strategies must beat with costs.

## 6. Risks
- Volatility 2–5x equities — requires wider stops and smaller position units;
  reflect in per-market risk limits (`pyrobot/data/sectors.py`).
- Correlation to equities has risen since 2020 (risk-on behavior).
- Exchanges API-differ; yfinance daily is fine for backtests, real-time needs
  CCXT and exchange-native calendars.
- Shorting carries borrow cost (charged at 1.0% p.a. placeholder in the honest
  backtester) and, in practice, exchange/platform availability constraints.

## 7. Cost Model
- `ExecutionCostModel`: spread (~0.05–0.10%), slippage (±1 tick on next-bar
  open), commission, SEC fee (sell side), 10% volume-participation cap, and
  per-bar borrow/carry on open shorts. Parameters are placeholders pending a
  counterparty contract.

## 8. Decision
- [x] APPROVED — proceed to Wave implementation (executed in Wave 1; revalidated
  with honest short-side accounting in Wave 5). No live trading.
- Note: revalidated 5y results: crypto_trend +2.8%, crypto_mean_rev −3.4% vs
  crypto Buy & Hold +18.0% — see `AI_Quant_Multi_Market_Advisory_Report.md` §3.

## 9. Impact on Code
- `pyrobot/data/crypto_provider.py` — CryptoProvider + 24/7/365 calendar + quality.
- `pyrobot/data/sectors.py` — crypto sector classification (Wave 5).
- `pyrobot/strategies/crypto_trend.py`, `crypto_mean_rev.py` — strategies.
- `backtest_crypto_trend.py`, `backtest_crypto_mean_rev.py` — honest backtests.
- `crypto_paper_session.py` — paper session.
- `pyrobot/backtesting/runner.py`, `cost_model.py` — honest short accounting + borrow.
- `data/reports/*crypto*`, `data/audit/*crypto*` — reports & audit trail.

## 10. Post-hoc Acknowledgment (required by Wave 5 governance)
- **Sequence breach:** this memo is written **after** the market was implemented
  (Wave 1, 2026-09-09), violating §9 of the wave order (memo first). The
  governing standard (`docs/professional_development_standard.md`) requires
  research-before-building; that gate was not applied to this market's
  engineering decision.
- **Lessons learned:**
  1. Backtests originally used `periods_per_year=252`, under-annualizing Sharpe
     for a 365-day market; corrected to 365 in both crypto scripts.
  2. The `on_order_fill` direction bug also affected crypto strategies; caught by
     the same synthetic short round-trip test during Wave 5.
  3. Future crypto engineering: memo first, 365-day annualization by default,
     and explicit exchange-calendar handling before any intraday work.
- **Verified by:** Wave 5 pre-push checklist (memo present, format valid, linked
  from `continuous_research_log.md`).