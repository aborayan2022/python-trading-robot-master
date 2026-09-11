# AI Quant Multi-Market Advisory Report

**التقرير الاستشاري الشامل لحالة المنصة متعددة الأسواق**

| | |
|---|---|
| **Project** | `python-trading-robot-master` |
| **Plan** | `AI_Quant_Trading_Platform_Multi_Market_Wave_Prompt.md` (v0.2.0 → Multi-Market) |
| **Report date** | 2026-09-10 |
| **Prepared by** | Programmer Team Leader (review & completion of interrupted final task) |
| **Status** | **COMPLETE — all 5 waves implemented, Wave 5 remediation & revalidation delivered, 561 tests green** |
| **Headline** | 3 markets × 7 strategies, bi-directional, cost-adjusted, benchmark-compared. **Wave-5 revalidation with real short-side execution shows NO strategy beats Buy & Hold on its own market in the 2021–2026 window** (best: `us_trend` +91.9% vs B&H +195.1%). The earlier "+134%" `metals_trend` figure was an artifact of a runner that silently dropped short orders — it is retracted. |

---

## 0. Executive Summary

The Multi-Market Wave Directive was **95% implemented** when a power outage interrupted the session **during the final task (Wave 4 — final advisory report + last verification)**. The work was `git add`-ed but **never committed**; `reports/AI_Quant_Multi_Market_Advisory_Report.md` was missing; and the Wave-4 test file failed 6 tests.

The team reviewed the full plan against the repository, completed the remaining work, **fixed 4 real defects** left by the interrupted session, and (in **Wave 5**) hardened the honest-short accounting, fixed a direction-handling bug in 6 strategies' fill callbacks, re-ran all six full backtests, and regenerated every aggregation report. This edition supersedes the earlier report circulated at commit `d050f3d`.

### Was the plan successfully implemented?

**Yes — functionally complete and green.** The Wave-5 revalidation then corrected a runner defect (shorts were never truly executed, inflating the old "$+134\%$" claim) and re-reported every strategy with honest short-side accounting:

| Dimension | Verdict |
|---|---|
| Wave 0 — Education (3 markets + 3 strategies + glossary + research log + UI cards) | ✅ Complete |
| Wave 1 — Multi-market data layer (metals + crypto providers, registry, calendars, quality) | ✅ Complete (after 2 bug fixes) |
| Wave 2 — Strategy suite (registry + 6 new strategies, Long+Short) | ✅ Complete (after 1 bug fix) |
| Wave 3 — Backtest + paper sessions per market (6 backtests, 2 paper sessions, audit) | ✅ Complete (after runner fix + data refresh) |
| Wave 4 — ML/regime/weekly-research/UI/CI/Docker + **final advisory report** | ✅ Complete (final task executed here) |
| **Proven Edge (Rule 2 / Rule 5 of the directive)** | ⚠️ **None — no strategy beats its market's Buy & Hold with costs** |

The platform is exactly what the directive's Section 7 asks for *in structure*: Multi-Market, Multi-Strategy, Bi-Directional (now with genuinely executed and closed shorts), Cost-Adjusted, Benchmark-Compared, Regime-Aware, Risk-Controlled, Audit-Trailed, Paper-Tested (NOT Live). **In edge quality** it currently demonstrates no cost-adjusted edge over Buy & Hold — which must be honestly reported to the consultant rather than hidden.

---

## 1. What was implemented (per Wave)

### Wave 0 — Education (Goal A) — Complete
- `docs/education/01_stocks_foundations.md`, `02_metals_foundations.md`, `03_crypto_foundations.md`
- `docs/education/04_strategy_trend_follow.md`, `05_strategy_mean_reversion.md`, `06_strategy_breakout.md`
- `docs/education/glossary_ar_en.md` (Arabic/English glossary)
- `reports/continuous_research_log.md` — 2 new market entries (Metals, Crypto) with sources, findings, decisions
- `pyrobot/console/static/index.html` — market cards activated, **no "Coming Soon"** left

### Wave 1 — Data Layer (Goal B) — Complete
- `pyrobot/data/metals_provider.py` — `MetalsProvider` (GC=F, SI=F, GLD, SLV) via yfinance, COMEX calendar
- `pyrobot/data/crypto_provider.py` — `CryptoProvider` (BTC-USD, ETH-USD) via yfinance, **24/7/365 calendar**
- `pyrobot/data/registry.py` — `DataProviderRegistry` + `PYROBOT_MARKET` env selection
- Cached data: `data/metals/*.csv`, `data/crypto/*.csv` (5-year daily, refreshed)
- `pyrobot/data/quality.py` per-market quality checks
- `tests/test_data_quality_multi_market.py` — 18 tests

### Wave 2 — Strategy Suite (Goal C) — Complete
- `pyrobot/strategies/registry.py` — `StrategyRegistry` factory + env selection (`PYROBOT_STRATEGY`)
- New strategies (all inherit `MultiSymbolStrategy`, all have `DEFAULT_PARAMETERS`):
  - `us_mean_reversion.py` `USMeanReversionStrategy` (Long+Short)
  - `us_breakout.py` `USBreakoutStrategy` (Long+Short)
  - `metals_trend.py` `MetalsTrendFollowStrategy` (Long+Short)
  - `metals_momentum.py` `MetalsMomentumBreakout` (Long+Short)
  - `crypto_trend.py` `CryptoTrendBreakoutStrategy` (Long+Short)
  - `crypto_mean_rev.py` `CryptoMeanReversionStrategy` (Long+Short)
- `tests/test_multi_market_strategies.py` — 20 tests (registry + warm-up/toggle + pipeline)

### Wave 3 — Backtesting + Paper (Goal D) — Complete
- `pyrobot/backtesting/runner.py` — shared honest-backtest runner (next-bar open, `ExecutionCostModel`, Buy&Hold bench, runtime replay via Pipeline/Loop)
- 6 backtest scripts: `backtest_us_mean_reversion.py`, `backtest_us_breakout.py`, `backtest_metals_trend.py`, `backtest_metals_momentum.py`, `backtest_crypto_trend.py`, `backtest_crypto_mean_rev.py` — all include `--dry-run`
- 2 paper sessions: `metals_paper_session.py` (COMEX) and `crypto_paper_session.py` (24/7) — both include `--smoke`
- Reports in `data/reports/` (backtest + paper + `multi_market_comparison.json` + `strategy_validation.json`)
- Audit logs in `data/audit/` (metals + crypto `*.jsonl`)

### Wave 4 — Deployment (Goal E) — Complete (this review completed the final tasks)
- `pyrobot/ai/training.py` — `market` support confirmed
- `pyrobot/features/regime.py` — `RegimeStrategyMatcher` (market→regime→strategy + position sizing) added
- `scripts/weekly_research.py` — multi-market benchmark rendering + comparison aggregation
- `scripts/multi_market_comparison.py` + `scripts/strategy_validation.py` (Walk-Forward presence + 1000-run Monte Carlo per strategy)
- `.github/workflows/ci.yml` — new `multi-market-smoke` job (backtest dry-runs + paper smokes)
- `docker-compose.yml` — multi-market profiles (`PYROBOT_MARKET`); `docker compose config` **OK**
- `pyrobot/console/static/index.html` — all cards live, no "Coming Soon"
- `reports/AI_Quant_Multi_Market_Advisory_Report.md` — this file (was missing)

---

## 2. What the review found broken (post-outage) and fixed

| # | Defect | Impact | Fix |
|---|--------|--------|-----|
| 1 | **Final advisory report missing** (`4.8`) | Wave 4 incomplete | Written in this review |
| 2 | `tests/test_wave4_deployment.py` — 6 failures | CI red (4.6) | (a) Registry test class in `test_multi_market_strategies.py` called `StrategyRegistry.clear()` and never restored built-ins → cross-test pollution when run in alphabetical order. Extracted `register_builtin_strategies()` and restore it in `setup_method`. (b) 3 test bugs fixed: pass a real `RegimeState` to `matcher.recommend`, provide full OHLCV to the regime-detector frame. |
| 3 | **Breakout strategies never traded** (us_breakout, metals_momentum, crypto_trend → 0 trades) | Wave 3 results misleading | Off-by-one: `closes.iloc[-lookback:].max()` includes the *current* close, making `close > high_close` mathematically **impossible**. Changed to prior-window `iloc[-(lookback+1):-1]` in all 3 strategies. Now trade normally. |
| 4 | **Stale caches** — `GC_F.csv`, `BTC_USD.csv` were 100-row partials (2021-01→04) with zero overlap vs peers | metals/crypto backtests crashed with `KeyError: Timestamp('2021-01-01')` | Refreshed full 5-year caches via yfinance. |
| 5 | **`MultiMarketBacktest.honest_backtest`** — union timestamps with `.loc` on every symbol | crash if one symbol lacks a day | Skip symbols without a bar at that timestamp (robust alignment). |
| 6 | **`download_all(refresh=True)`** never re-downloaded (only cleared memory cache; stale CSV re-read) | refresh unusable | Thread `refresh` through `_load_or_download` in both providers to overwrite CSV. |
| 7 | `CryptoProvider.TRADING_CALENDAR` not a class attribute (criteria `1.5` literal check) | acceptance check failed | Added class-level constant on both providers. |
| 8 | Aggregators included `--dry-run` (200-bar) reports as "results" | comparison polluted by wiring checks | Skip `dry_run` reports; keep latest honest full run per strategy. |
| 9 | 3 ruff errors in `pyrobot/` (would fail CI lint step) | CI red | Fixed (unused import + 2 unused locals). |
| 10 | **`d050f3d` runner routed `SELL_SHORT` through the `SELL` exit branch** — shorts silently dropped when flat, or *closed* an open long at a short signal | old results were long-only / sequence-corrupted | Full short side executed & closed (`SELL_SHORT`/`BUY_TO_COVER`); per-bar borrow charge (1.0% p.a. placeholder) accrued on open short notional; short proceeds and closing PnL accounted with cash. |
| 11 | **Direction bug in `on_order_fill` for all 6 new strategies** — `SELL_SHORT` treated as exit, `BUY_TO_COVER` as entry | shorts never entered holding state → could never be exited | `BUY`/`SELL_SHORT` → entry, `SELL`/`BUY_TO_COVER` → exit; pipeline passes `order.side.value` into the callback. |
| 12 | Per-symbol bar counts, stop-loss enforcement, and short trailing-exit tracking defects | miscounts/wrong exits | Per-symbol `_bar_count` in 5 strategies; stops enforced in `crypto_mean_rev`/`us_mean_reversion`; correct short trailing exit (`_lowest_since_entry`) in `us_breakout`; `periods_per_year=365` in both crypto backtest scripts. |
| 13 | Aggregators: `market_count` was 7 (no market grouping) and duplicate `USTrendFollowStrategy` rows | comparison report misleading | `MARKET_GROUPS` (US/Metals/Crypto) + "keep latest report per strategy" dedup. |

---

## 3. Final honest backtest results (5y daily, next-bar-open fills, costs + short borrow included, vs Buy & Hold)

Market data: US 10 stocks / metals (GC=F, SI=F, GLD, SLV) / crypto (BTC-USD, ETH-USD), 2021-09 → 2026-09. **Wave-5 rehabilitation:** the runner now executes and closes `SELL_SHORT`/`BUY_TO_COVER` orders end-to-end and charges borrow/carry on open shorts (1.0% p.a.); all six strategies' `on_order_fill` callbacks correctly map `BUY`/`SELL_SHORT` → entry and `SELL`/`BUY_TO_COVER` → exit. Figures below are the honest, revalidated results.

| Strategy | Market | Return | Buy & Hold | Sharpe | MaxDD | Trades | WinRate | Beats B&H? |
|---|---|---|---|---|---|---|---|---|
| **us_trend** (existing) | US | **+91.91%** | +195.08% | 1.19 | -15.1% | 631 | 64.5% | ❌ |
| crypto_trend | Crypto | +2.19% | +18.0% | 0.17 | -4.6% | 13 | 61.5% | ❌ |
| us_mean_reversion | US | −0.05% | +195.08% | 0.04 | -13.2% | 343 | 43.4% | ❌ |
| crypto_mean_rev | Crypto | −3.40% | +18.0% | -0.35 | -4.3% | 16 | 37.5% | ❌ |
| us_breakout | US | −11.52% | +195.08% | -0.35 | -17.1% | 126 | 31.8% | ❌ |
| metals_trend | Metals | −57.48% | +136.26% | -0.41 | -73.6% | 442 | 31.2% | ❌ |
| metals_momentum | Metals | −11.97% | +136.26% | -0.52 | -15.2% | 75 | 21.3% | ❌ |

> **Why the earlier +134% `metals_trend` figure is retracted:** commit `d050f3d`'s runner routed `SELL_SHORT` orders through the plain `SELL` (exit) branch — if no long was open the order was silently dropped, and if a long was open it was *closed* at the short signal. No short was ever actually opened. Combined with a (since-fixed) `metals_trend.on_order_fill` bug that treated `SELL_SHORT` as an exit and `BUY_TO_COVER` as an entry, the old numbers were effectively a subset of long-only behavior. Restoring true short execution and exit bookkeeping is what the honest metals/other results above reflect. Shorts can now both open and close, and borrow/carry is charged per bar on open short notional.

> **Follow-up re-run (2026-09-11):** the interim metals figure (−17.58% / 275 trades) shipped in commit `a542855` was produced from an intermediate working-tree state (runner short-side / accounting edits still in flight) and does **not** reproduce against the committed code. All six strategy backtests were re-run in full from committed HEAD (files `data/reports/*_backtest_20260910_*/20260911_*.json`); the numbers in this section reflect those runs. Net effect: `metals_trend` degrades to −57.5% and `metals_momentum` improves to −12.0%; nothing crosses the buy-and-hold bar, and the short-side conclusion is unchanged but stronger.

### Monte Carlo stress (bootstrap over realized trade PnLs, 1000 sims, $100k, ruin = 25% drawdown)

| Strategy | Median return | Worst-5% (p5) | Ruin prob |
|---|---|---|---|
| us_trend | +49.1% | +21.3% | 0.1% |
| crypto_trend | +2.3% | −3.6% | 0.0% |
| us_mean_reversion | +0.8% | −20.2% | 5.1% |
| crypto_mean_rev | −3.4% | −8.8% | 0.0% |
| us_breakout | −11.3% | −25.0% | 9.3% |
| metals_trend | −39.4% | −51.0% | **99.0%** |
| metals_momentum | −12.3% | −25.4% | 7.3% |

> Note: only `us_trend` and `crypto_trend` have positive Monte-Carlo medians, and `us_trend` alone is positive at the 5th percentile. `metals_momentum` shows a 7.3% ruin probability and `metals_trend` a **99.0%** ruin probability — the weakest profile in the suite by far. The patterns are consistent with single-market momentum/trend-following substantially lagging buy-and-hold through the 2021–2026 equity/metals rally, while paying spread+fee drag and (for metals) borrow on unprofitable short trades. `metals_trend` reinforces the short-side drag finding: ratcheted exits plus many small partial-fill churn trades turned its long/ short book into a −57.5% round trip.

---

## 4. Acceptance criteria compliance

| Wave | Criteria | Result |
|---|---|---|
| 0.1–0.7 | docs exist, research-log entries, cards, no new bare `.py` in education | ✅ (see §1) |
| 1.1–1.8 | providers, registry, data, 24/7 calendar, quality tests | ✅ `pytest tests/test_data_quality_multi_market.py` = 18 passed |
| 2.1–2.10 | registry, 6 strategies, inherit + params, tests, env selection | ✅ `pytest tests/test_*_strategy.py` = 20 passed |
| 3.1–3.10 | 6 backtests (B&H + cost), 2 paper sessions, reports/audit | ✅ all `--dry-run` exit 0, smokes exit 0 |
| 4.1–4.10 | ML/regime/weekly/UI/CI/docker/report + **no live trading + no gate-bypass** | ✅ `pytest tests/` = **561 passed**; `docker compose config` OK; no `skip_gate`; no live-trading path in new code |

**Full suite: `python -m pytest tests/` → 561 passed, 2 warnings (pre-existing deprecation notices).**

---

## 5. Assumptions made

1. **Paper only** — no live trading was introduced anywhere; the remaining `LIVE` strings are pre-existing console gating behind `PYROBOT_ALLOW_LIVE_TRADING=true` (outside this plan's scope).
2. "Honest backtest" = fills at **next bar open** using `ExecutionCostModel` (spread, slippage, commission, SEC fee, participation caps); no look-ahead beyond the fixed warm-up indicators.
3. Crypto/metals data via **yfinance** (accepted by the directive as the primary source); daily bars, not intraday.
4. Regime→strategy mapping and position scaling constants (0.25–1.0) are **rule defaults**, not ML-tuned.
5. The two `us_trend` backtest reports in `data/reports/` are pre-existing project artifacts (kept as historical evidence); the 6 new-strategy reports were regenerated on corrected data.
6. The 6 new-strategy reports were **re-run in full** for Wave 5 (final stamp `20260911_00xxxx`); older reports (including the `20260910_16xxxx` batch and `_superseded_20260909_` artifacts) are retained for audit but are superseded. Short borrow uses 1.0% p.a. as a placeholder rate until the broker/counterparty contract is known.

---

## 6. What remains risky (honest list)

1. **No strategy beats Buy & Hold with costs in this window.** By the directive's own Rule 2/5/8, none of the 7 survives the "beat Buy & Hold after costs" test on 2021–2026 daily data. The platform should **not** be marketed as multi-market alpha; treat every strategy as unproven until out-of-sample/walk-forward validation is attached.
2. **Short-side drag is now material.** True short execution + borrow + low short-side win rates drive most of the degradation vs the old long-only figures (e.g., `metals_trend` now trades 442 times at 31.2% win for −57.5% vs the old 66-trade long-only subset). The sell logic, not just the accounting, needs rework before any short book is defensible.
3. **Parameterization is default-only.** No walk-forward tuning was performed on the 6 new strategies (prohibition: no tuning on the test set). Nearest to positive: `crypto_trend` (+2.2%, 61.5% win) and `us_mean_reversion` (−0.05%, positive MC median). Weakest: `metals_trend` (99.0% ruin).
4. **Data quality**: futures volume for GC=F/SI=F has small pockets of zero-volume days (data artifact, not fatal); crypto/metals caches are one-refresh-old; no futures contract roll handling (CME GC/SI have no roll logic in `metals_provider.py`).
5. `StrategyRegistry.clear()` remains a footgun for tests if the registry is not re-populated (mitigated by `register_builtin_strategies()`).
6. Docker Compose validated locally with `docker compose config` (v2). The literal `docker-compose` (v1) binary was not installed on the review machine; CI does not run compose, so real container startup remains unverified.
7. Mypy full-tree debt is pre-existing (~130 errors) and explicitly non-blocking in CI; the enforced module set passes (`ruff check pyrobot/` → clean).

---

## 7. Performance, security, migration

**Performance:** Backtests are compute-bound (full 5-year run ≈ 0.5–6 min/strategy; `us_mean_reversion` at ~15 min is the outlier; TradingLoop runtime replay dominates printing). No production live path, so no infrastructure risk.

**Security:** No secrets added; no live-trading unlock; audit ledger remains cryptographically signed; console live-trading remains locked by env var. Aggregators write only local JSON.

**Migration:** None required. New env switches: `PYROBOT_MARKET` / `PYROBOT_STRATEGY` / `PYROBOT_UNIVERSE` / `PYROBOT_DATA_DIR`. Cache format unchanged (CSV, `datetime` index).

---

## 8. Recommendations to the consultant

1. **Approve the structural completion** (5 waves, Wave 5 remediation, 561 tests green) — the multi-market **platform** is built, honest, and safe (paper-only).
2. **Do not approve any "edge" claim.** Require walk-forward + Monte Carlo acceptance per strategy/market before any scaling. Current data supports **research** (not deployment) for `crypto_trend` and `us_trend`.
3. **Next quarter (next wave) priorities**, in order:
   - Walk-forward parameter research focused on `crypto_trend`, `us_mean_reversion`, `us_trend` (closest to a positive cost-adjusted profile);
   - Rework the short-side logic in the metals/US strategies (low short win rate + borrow drag), then revalidate; until then, cap or disable shorts;
   - **Retire or rewrite** `metals_trend` per Rule 5 (99.0% MC ruin on the honest short-included run — quality over quantity); keep `metals_momentum` (7.3% ruin) research-only;
   - Add CME futures roll handling to `metals_provider.py` and re-run metals windows;
   - Expand paper sessions to run on schedule (cron) so live market conditions feed the audit trail;
   - Wire `RegimeStrategyMatcher` output into position sizing in the live pipeline (currently advisory-only).
4. **CI/docker**: add a compose config step + walk-forward regression gate before merging future strategy changes.

---

## 9. Appendix — verification commands (all pass)

```bash
python -m pytest tests/ -v                      # 561 passed
for b in backtest_us_mean_reversion backtest_us_breakout \
         backtest_metals_trend backtest_metals_momentum \
         backtest_crypto_trend backtest_crypto_mean_rev; do python $b.py; done   # Wave-5 full honest reruns
python scripts/multi_market_comparison.py       # 7 strategies across 3 markets
python scripts/strategy_validation.py           # walk-forward presence + 1000-run Monte Carlo
ruff check pyrobot/                            # All checks passed
docker compose config                          # OK
python -c "from pyrobot.data.crypto_provider import CryptoProvider; print(CryptoProvider.TRADING_CALENDAR)"
```

---

**End of report — AI Quant Multi-Market Advisory Report.**