# Decision Memo: Precious Metals

**Date:** 2026-09-10 (post-hoc — see §10)
**Requested by:** Programmer Team Leader (Wave 1 — Multi-Market expansion)
**Market:** Metals (COMEX gold & silver futures via GC=F, SI=F; ETFs GLD, SLV)

## 1. Why this market?
- Precious metals are a distinct asset class with low historical correlation to
  US equities, providing portfolio diversification for the multi-market mandate.
- Metals have well-defined, globally traded reference instruments (COMEX
  futures) plus liquid ETF proxies (GLD, SLV) that simplify daily-bar data work.
- The directive's Rule on multi-market breadth explicitly names metals as one of
  the expansion targets.

## 2. Data Source
- yfinance tickers: `GC=F` (gold futures), `SI=F` (silver futures), `GLD`
  (SPDR Gold Trust), `SLV` (iShares Silver Trust).
- Cached to `data/metals/*.csv` (5-year daily OHLCV, UTC).
- Reference: CME Group COMEX contract specifications; GLD/SLV prospectuses.

## 3. Trading Calendar
- COMEX Globex: ~23h/day, Sunday 18:00 ET → Friday 17:00 ET, with a daily
  17:00–18:00 ET maintenance break. Modeled as a daily calendar in
  `MetalsProvider.TRADING_CALENDAR`; used for paper-session bar scheduling.
- Daily-bar backtests align on union timestamps across the four tickers.

## 4. Expected Strategies
- `MetalsTrendFollowStrategy` (`metals_trend.py`) — trend following, LONG+SHORT.
- `MetalsMomentumBreakout` (`metals_momentum.py`) — momentum/breakout, LONG+SHORT.

## 5. Benchmark
- Investable equal-weight Buy & Hold over the four tickers, cost-adjusted
  (`runner.buy_and_hold_benchmark`), each symbol entered at its own first bar.
- Reference window 2021-09 → 2026-09 returns **+136.26%** for the revalidated
  runner — this is the bar any metals strategy must beat with costs.

## 6. Risks
- Futures volume for GC=F / SI=F shows small pockets of zero-volume days
  (data artifact) — handled by volume-participation caps in the cost model.
- **No contract-roll handling** in `metals_provider.py` — front-month GC/SI data
  can embed roll jumps; documented, not yet mitigated.
- USD real-rate and dollar-strength sensitivity; regime-dependent volatility.
- Short-selling metals ETFs/futures carries borrow/carry cost (charged in the
  honest backtester at 1.0% p.a. placeholder).

## 7. Cost Model
- `ExecutionCostModel`: spread (~0.05–0.10%), slippage (±1 tick on next-bar
  open), commission, SEC fee (sell side), 10% volume-participation cap, and
  per-bar borrow/carry on open shorts. Parameters are placeholders pending
  broker/counterparty contract.

## 8. Decision
- [x] APPROVED — proceed to Wave implementation (executed in Wave 1; revalidated
  with honest short-side accounting in Wave 5). No live trading.
- Note: revalidated 5y results show neither metals strategy beats the metals
  Buy & Hold benchmark (metals_trend −17.6%, metals_momentum −19.8%) — see
  `AI_Quant_Multi_Market_Advisory_Report.md` §3.

## 9. Impact on Code
- `pyrobot/data/metals_provider.py` — MetalsProvider + COMEX calendar + quality.
- `pyrobot/data/sectors.py` — metals sector classification (Wave 5).
- `pyrobot/strategies/metals_trend.py`, `metals_momentum.py` — strategies.
- `backtest_metals_trend.py`, `backtest_metals_momentum.py` — honest backtests.
- `metals_paper_session.py` — paper session.
- `pyrobot/backtesting/runner.py`, `cost_model.py` — honest short accounting + borrow.
- `data/reports/*metals*`, `data/audit/*metals*` — reports & audit trail.

## 10. Post-hoc Acknowledgment (required by Wave 5 governance)
- **Sequence breach:** this memo is written **after** the market was implemented
  (Wave 1, 2026-09-09), violating §9 of the wave order which requires the memo
  **before** implementation. The governing standard
  (`docs/professional_development_standard.md`) was ratified 2026-09-06 and its
  "research before building" rule was not applied to this market's engineering
  gate.
- **Lessons learned:**
  1. The original backtest figures were unreliable because shorts were never
     truly executed (runner routed `SELL_SHORT` to the SELL branch); revalidation
     had to be built, not assumed.
  2. The `on_order_fill` direction bug (`SELL_SHORT` treated as exit) existed in
     every new strategy and only surfaced under a synthetic short-round-trip test.
  3. Any future market entry: memo first (this exact format), data-quality and
     strategy tests before backtests, and honest two-sided execution by default.
- **Verified by:** Wave 5 pre-push checklist (memo present, format valid, linked
  from `continuous_research_log.md`).