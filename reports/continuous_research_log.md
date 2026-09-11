# Continuous Research Log

**Purpose:** every research question, its sources, the findings, and the concrete
decision it produced — linked to the code it impacted. This is the enforcement
trail for the "Research Before Building" standard
(`docs/professional_development_standard.md`).

**Maintenance:** the weekly research session (Saturdays 10:00) scans the reference
library for updates / reported errors, appends new entries, and links lessons to the
task list.

---

## Entry Template

```markdown
## YYYY-MM-DD — <short question>

**Question:**

**Sources:**
- <url / citation>

**Findings:**
- ...

**Comparison with our use case:**
- ...

**Decision / Lesson:**
- ...

**Impact on code:**
- `file/path.py` — what changed (or "none — decision only")
- test: `tests/...`
```

---

# Entries

## 2026-09-06 — Are we re-implementing AFML from scratch?

**Question:** Is the project's labeling and cross-validation approach redundant with
established references, and where should we align instead of reinventing?

**Sources:**
- López de Prado, *Advances in Financial Machine Learning* (2018), ch. on Triple-Barrier labeling, Purged & Embargoed K-Fold, Combinatorial Purged CV, and backtesting.
- mlfinlab (Hudson & Thames) — open-source reference implementation of AFML.
- Independent trading-bot failure surveys (7 documented pitfalls; ~70–80% failure estimates).

**Findings:**
- Our `ai/labels.py` Triple-Barrier scheme matches the book's labeling method.
- Our `walk_forward.py` purge/embargo matches the book's leakage-prevention concept.
- The book recommends **Combinatorial Purged Cross-Validation** specifically to answer
  "is the result luck?" — we have not implemented CPCV yet.
- mlfinlab is a tested, community-used implementation we can run parity tests against.

**Comparison with our use case:**
- We target daily large-cap US equities with a directional ML ensemble; the book covers
  the same family of problems and precedes our work, so its advice is directly applicable.

**Decision / Lesson:**
- Stop reinventing; read the CV/backtesting chapters before designing the next experiment.
- Add CPCV to `walk_forward.py` as the answer to "were the 631 trades luck?".
- Use mlfinlab for mathematical verification of Triple-Barrier / purging (Track 2).

**Impact on code:**
- `pyrobot/backtesting/walk_forward.py` — CPCV module under development (Quarterly Plan Track 1).
- `reports/خطة_التطوير_المهني.md` — Tracks 1 & 2.

---

## 2026-09-06 — Should we build a multi-asset execution layer from scratch vs. NautilusTrader?

**Question:** The previous GM asked about new markets (Egyptian exchange, metals, crypto).
Is extending our hand-written broker adapters the right path vs. building on a mature engine?

**Sources:**
- NautilusTrader official documentation (Rust engine, Python API, AI-first design).
- Adapter architecture docs: REST / WebSocket / FIX adapters for FX, equities, futures, options, CFDs, crypto.

**Findings:**
- NautilusTrader is production-grade and multi-asset out of the box; the same strategy code runs
  in backtest and live without modification.
- Our current design builds a separate broker adapter per venue by hand.

**Comparison with our use case:**
- Our differentiator is the predictive model + governance/risk layer, not the execution plumbing.
- Building adapters for every new venue duplicates months of non-differentiating engineering.

**Decision / Lesson:**
- Before expanding to any new market, write the **NautilusTrader decision memo**
  (build-on-top vs. custom execution layer). This is a mandatory gateway.
- No new-market code until the memo exists and a decision is recorded here.

**Impact on code:**
- `reports/خطة_التطوير_المهني.md` — Track 3 (NautilusTrader Decision Memo).
- No adapter code until the memo decision.

---

## 2026-09-06 — The seven documented pitfalls — where do we stand?

**Question:** Which of the widely documented automated-trading failure modes still applies to us?

**Sources:**
- Independent trading-bot failure surveys (multiple sources, mutually consistent).

**Findings (per pitfall, vs. our code):**
1. Overfitting — economic gate rejected 3 decorated models in a row (guarded, keep re-checking).
2. Look-ahead bias — next-bar execution implemented (fixed).
3. Transaction costs — `ExecutionCostModel` mandatory (fixed).
4. Risk management — kill switch + circuit breaker exist but untested under live pressure.
5. Data quality — yfinance is experiment-only; production is Alpaca. Verify source per market.
6. Forward testing — not started; this is exactly the current paper-trading phase.
7. Unrealistic expectations — honest "no baseline-beating" reporting on record.

**Comparison with our use case:**
- The project already avoids most of the seven, largely because it responded to
  successive technical reviews — a strong survival indicator vs. the industry average.

**Decision / Lesson:**
- Codify the seven-pitfall table as the recurring release checklist
  (adopted in `docs/professional_development_standard.md` §3).
- The remaining gaps (#4 risk-under-pressure, #6 forward-testing) drive the live paper-trading phase.

**Impact on code:**
- `docs/professional_development_standard.md` — recurring release checklist.
- `docs/production_runbook.md` — paper-trading acceptance gate (3–6 months).
```
---

## 2026-09-07 — Weekly research session (scheduled)

**Question:** Pending follow-up scan of the reference library.

**Sources:** Pending.

**Findings:**
- 2026-09-07: scheduled weekly research session ran.
- Scan the reference library for updates / reported errors, then replace this
  stub with the findings, comparison, and decision (see the Entry Template above
  and the seven-pitfall checklist in `professional_development_standard.md`).

**Comparison with our use case:** Pending.

**Decision / Lesson:** Pending.

**Impact on code:**
- none — decision pending.

---

## 2026-09-09 — Precious Metals: market characteristics and data source

**Question:** What are the characteristics of precious metals markets, and what
data source should we use for backtesting and paper trading?

**Sources:**
- CME Group COMEX documentation (gold, silver futures specifications).
- yfinance documentation for commodity futures tickers (GC=F, SI=F).
- GLD (SPDR Gold Trust) and SLV (iShares Silver Trust) ETF prospectuses.

**Findings:**
- Gold (GC=F) and Silver (SI=F) futures trade on COMEX via Globex nearly 23h/day.
- yfinance provides reliable daily OHLCV for GC=F, SI=F, GLD, SLV.
- Metals are priced in USD — inverse correlation with dollar strength.
- Volatility is regime-dependent: low in stable macro, high in crisis.
- ETFs (GLD, SLV) provide simpler data handling vs. futures roll costs.

**Comparison with our use case:**
- Our existing `DataQualityEngine` handles daily OHLCV validation and can
  work with metals data without modification.
- Metals' ~23h trading window overlaps with US equity hours (9:30-16:00 ET),
  so our existing timezone handling is compatible.

**Decision / Lesson:**
- Use yfinance for metals data (GC=F, SI=F, GLD, SLV) as primary source.
- Store in `data/metals/` directory.
- Include both futures and ETF tickers for robustness.
- Write educational foundation in `docs/education/02_metals_foundations.md`.

**Impact on code:**
- `pyrobot/data/metals_provider.py` — new metals data provider.
- `data/metals/` — new storage directory.
- `docs/education/02_metals_foundations.md` — new educational document.

---

## 2026-09-09 — Cryptocurrency: market characteristics and data source

**Question:** What are the characteristics of cryptocurrency markets, and what
data source should we use for backtesting and paper trading?

**Sources:**
- Bitcoin and Ethereum market structure research.
- yfinance documentation for crypto tickers (BTC-USD, ETH-USD).
- CCXT library documentation for exchange connectivity.

**Findings:**
- Crypto trades 24/7/365 with no market close or holidays.
- yfinance provides daily OHLCV for BTC-USD, ETH-USD (back to 2014 for BTC).
- Crypto volatility is 2-5x that of equities — requires wider stops.
- Market is younger (~15 years) — less historical data for regime analysis.
- Correlation to equities has increased since 2020 (risk-on asset behavior).

**Comparison with our use case:**
- Our `TradingPipeline` and `TradingLoop` are timezone-agnostic — they work
  with any daily bar sequence regardless of market hours.
- yfinance data is sufficient for daily backtesting; CCXT would be needed
  for intraday or real-time (future enhancement).

**Decision / Lesson:**
- Use yfinance for crypto data (BTC-USD, ETH-USD) as primary source.
- Store in `data/crypto/` directory.
- Plan for CCXT integration when moving to intraday timeframes.
- Write educational foundation in `docs/education/03_crypto_foundations.md`.

**Impact on code:**
- `pyrobot/data/crypto_provider.py` — new crypto data provider.
- `data/crypto/` — new storage directory.
- `docs/education/03_crypto_foundations.md` — new educational document.

---

## 2026-09-09 — Multi-market strategy architecture: registry and factory pattern

**Question:** How should we architect the strategy layer to support multiple
markets and strategies without manual linking?

**Sources:**
- `pyrobot/strategies/base.py` — existing BaseStrategy/MultiSymbolStrategy.
- `pyrobot/runtime/pipeline.py:34` — TradingPipeline accepts BaseStrategy.
- Gang of Four: Factory Method pattern; Abstract Factory for product families.

**Findings:**
- Current design: `build_alpaca_pipeline` manually wires one strategy.
- No registry: adding a new strategy requires editing the pipeline builder.
- `TradingPipeline.signal_source` accepts `BaseStrategy | EnsembleSignalEngine`.
- Strategy classes already follow a consistent interface (on_bar, on_order_fill).

**Comparison with our use case:**
- A StrategyRegistry with Factory Pattern would decouple strategy selection
  from pipeline construction.
- Environment variable selection (PYROBOT_STRATEGY) enables script-level
  configuration without code changes.

**Decision / Lesson:**
- Create `pyrobot/strategies/registry.py` with StrategyRegistry class.
- Each strategy module registers itself via `StrategyRegistry.register()`.
- Pipeline builder uses `StrategyRegistry.create(name, symbols, params)`.
- No manual linking required — adding a new strategy file is sufficient.

**Impact on code:**
- `pyrobot/strategies/registry.py` — new StrategyRegistry.
- `pyrobot/strategies/__init__.py` — updated exports.
- `pyrobot/runtime/pipeline.py` — optional: use registry for strategy creation.


---

## 2026-09-10 — Wave-5 revalidation: why the first-round metal/crypto figures were unreliable

**Question:** The first advisory claimed `metals_trend` beat Buy & Hold (+134%).
Wave-5 remediation revalidation shows no strategy beats its benchmark. What was
wrong, and what does the verification procedure change?

**Sources:**
- `git show d050f3d:pyrobot/backtesting/runner.py` (old short-order handling).
- Synthetic short round-trip test (`/tmp/opencode/test_short_borrow.py`).

**Findings:**
- The `d050f3d` runner routed `SELL_SHORT` orders through the plain `SELL`
  (exit) branch: shorts were silently dropped when flat, or closed an open long
  at a short signal. Shorts were never genuinely opened — the short side was
  **untested**, matching the first report's own disclosure.
- All six new strategies' `on_order_fill` treated `SELL_SHORT` as an exit and
  `BUY_TO_COVER` as an entry, so when shorts *were* executable the strategy never
  entered the "holding" state — shorts could never be closed.
- Also fixed in Wave 5: per-symbol `_bar_count`, enforced stop-losses in the two
  mean-reversion strategies, correct two-sided trailing exit in `us_breakout`,
  `periods_per_year=365` for crypto, and borrow/carry accounting on open shorts.

**Comparison with our use case:**
- The honest-backtest claim ("two-sided, cost-adjusted") was structurally true
  but mechanically incomplete: execution of one side was broken. A passing
  strategy test suite did not cover order anatomy (which side opens / closes).

**Decision / Lesson:**
- Always treat "backtest is honest" as an **assertion to re-verify**, not a
  status flag. Wave 5 added direction-aware fill handling and synthetic short
  round-trip verification.
- `metals_trend` +134% is **retracted**; revalidated figures are in
  `AI_Quant_Multi_Market_Advisory_Report.md` §3 (best safe profile here:
  `us_trend` +91.9% long-only; `crypto_trend` +2.8%).
- Decision memos for metals and crypto are filed post-hoc
  (`reports/decision_memo_metals.md`, `reports/decision_memo_crypto.md`) and the
  verification procedure was added to `docs/professional_development_standard.md`.

**Impact on code:**
- `pyrobot/backtesting/runner.py` — honest two-sided short execution + borrow.
- All 6 strategy files — direction-correct `on_order_fill`; per-symbol bar counts.
- `pyrobot/backtesting/cost_model.py` — `estimate_borrow_cost`.
- `data/reports/*_backtest_20260910_16*.json` — revalidated full runs.
- test: `pytest tests/` (561 passed) + synthetic short round-trip.

---

## 2026-09-11 — Final-HEAD re-run correction (Wave 5 close-out)

**Observation:** the interim strategy figures referenced above (+2.8% crypto_trend,
−17.6%/−19.8% metals, captured from `20260910_16xxxx` runs) were produced against an
in-flight working tree and did **not** reproduce from the committed code once the Wave-5
remediation diff was closed. Per the lesson logged above ("always treat 'backtest is
honest' as an assertion to re-verify"), all six strategy backtests were re-run again from
committed HEAD.

**Result (authoritative, `data/reports/*_backtest_20260911_*.json` → §3 of the advisory):**
- `crypto_trend` +2.19%; `crypto_mean_rev` −3.40% (unchanged).
- `metals_momentum` −11.97% (improved from −19.8% under ratcheted stops).
- `metals_trend` −57.48% (degrades from −17.6%; high churn from partial-fill requeues +
  ratcheted exits, MC ruin probability 99.0%).
- `us_breakout` −11.52%, `us_mean_reversion` −0.05% (unchanged).
- No strategy beats Buy & Hold; short-side conclusion is unchanged but stronger.

**Decision / Lesson:**
- Validation numbers for a release must be regenerated **after** the final commit, not
  captured from the working tree during remediation; the earlier advisory + memos shipped
  stale figures. The advisory and both decision memos now carry the corrected numbers and
  note the superseded interim values explicitly.
- `scripts/strategy_validation.py` now selects the latest report by `generated_at`
  timestamp (not filename sort), so `_superseded_`-tagged audit artifacts can no longer
  displace the newest honest run.

**Impact on code:**
- `scripts/strategy_validation.py` — latest-report selection via `generated_at`.
- `data/reports/multi_market_comparison.json`, `data/reports/strategy_validation.json` —
  regenerated.
- `data/reports/*_backtest_20260911_*.json` — final honest full runs.

---

## 2026-09-11 (2nd) — Provenance & clean-tree rule (review follow-up)

**Observation:** the reviewer independently reproduced `metals_trend` (−57.48%, 442
trades) from clean HEAD, confirming the `20260911_00xxxx` batch. Two remaining gaps were
flagged and closed here: (a) the supervisor market profile could leak `PYROBOT_SYMBOLS`
(default `MSFT,AAPL`) into the metals/crypto provider, dataset, and strategy; and (b) no
report carried the git SHA or dirty-tree flag, so "run from clean HEAD" was only
verifiable by re-running.

**Changes:**
- Supervisor market profile derives symbols from the market provider's own defaults
  (`DEFAULT_METALS`/`DEFAULT_CRYPTO`); `PYROBOT_SYMBOLS` no longer reaches the provider,
  data cache, or strategy. Test asserts no `symbols` kwarg reaches `DataProviderRegistry.create`.
- Reports now embed `provenance: {git_commit, dirty_tree}` (`runner.py` +
  `us_strategy_backtest.py`); `dirty_tree` reflects only tracked-file changes, so
  sequential report batches don't self-flag. Governance rule added
  (`docs/professional_development_standard.md` §3b): provenance required, clean tree
  before claims, reproducibility check from recorded commit.
- `data/audit/ledger.jsonl` + `data/metrics/runtime_metrics.jsonl` untracked and git-ignored
  (live session artifacts — appended by every smoke/run, so they could never stay clean).
- Interim `20260910_16xxxx` reports renamed `*_backtest_superseded_20260910_*`.

**Final authoritative batch:** `data/reports/*_backtest_20260911_07xxxx.json`, produced by
running the six scripts from clean commit `522f98e` (`dirty_tree=false`), numbers identical
to the reviewer's reproduction figure-for-figure.

**Impact on code:**
- `pyrobot/console/supervisor.py` — market symbols from provider defaults.
- `pyrobot/backtesting/runner.py`, `us_strategy_backtest.py` — `_git_provenance()`.
- `docs/professional_development_standard.md` — §3b provenance/clean-tree rule.
- `tests/test_console.py`, `tests/test_multi_market_wave5.py` — market-isolation +
  provenance tests.
- `.gitignore`, `data/reports/*_superseded_20260910_*`, `data/audit/ledger.jsonl`,
  `data/metrics/runtime_metrics.jsonl` (untracked).

---

## 2026-09-11 — Weekly research session (scheduled)

**Question:** How do each market's strategies compare against their Buy & Hold benchmark this week?

**Sources:** Pending follow-up library scan.

**Findings:**
- 2026-09-11: scheduled weekly research session ran; aggregates regenerated
  (multi_market_comparison.py, strategy_validation.py) and provenance-verified.
**Multi-market benchmarks (Buy & Hold comparison):**

| Strategy | Market | Strategy % | Buy & Hold % | Outcome | Provenance |
|---|---|---:|---:|---|---|
| USTrendFollowStrategy | US | 91.91% | 195.08% | behind benchmark | OK |
| crypto_mean_rev | Crypto | -3.4% | 18.0% | behind benchmark | OK |
| crypto_trend | Crypto | 2.19% | 18.0% | behind benchmark | OK |
| metals_momentum | Metals | -11.97% | 136.26% | behind benchmark | OK |
| metals_trend | Metals | -57.48% | 136.26% | behind benchmark | OK |
| us_breakout | US | -11.52% | 195.08% | behind benchmark | OK |
| us_mean_reversion | US | -0.05% | 195.08% | behind benchmark | OK |

- Scan the reference library for updates / reported errors, then replace this
  stub with the findings, comparison, and decision (see the Entry Template above
  and the seven-pitfall checklist in `professional_development_standard.md`).

**Comparison with our use case:** Pending.

**Decision / Lesson:** Pending.

**Impact on code:**
- none — decision pending.


---

## 2026-09-11 (3rd) — Consultant approval: Wave 5 closed, controls wired in

**Decision (consultant verdict 2026-09-11):** Wave 5 is **APPROVED and closed** —
no further engine/strategy modifications without a brand-new report batch. Live
trading stays suspended; paper phase continues 3–6 months per `production_runbook`;
no new markets until the Wave 6 walk-forward analysis concludes.

**Controls executed in this commit batch (`8e63d87`):**
- **#2 Dry-run scheduled sessions:** `metals_paper_session.py` and
  `crypto_paper_session.py` cron jobs switched from `--now` (execution) to
  `--dry-run` (monitoring only, no broker orders) pending Wave 6 verdicts.
  metals_trend is slated for retirement (−57.5%, 99% MC ruin); crypto_trend stays
  research-only (+2.2%, 0% ruin). The two daily sessions remain as a verification
  structure; they are no longer strategy "execution". Crontab installed live.
- **#3 dirty_tree corollary:** `docs/professional_development_standard.md` §3b.5 —
  untracked-code blind spot documented; new `.py` must ship in the same batch as
  its reports; uncommitted-tree reports are never release aggregates.
- **#4a Walk-forward honesty:** `strategy_validation.json` no longer claims
  `available: true` without figures — `available: false`, `results: null` until
  Wave 6 populates them. (Independent verification note: this was double-checked
  by running the regenerated validation file this session.)
- **#6 Weekly gate:** `weekly_research.py` always regenerates both aggregates via
  subprocess, provenance-gates every strategy (PROVENANCE REJECTED → exit non-zero),
  and records rejections in the log stub. `us_trend` re-run from clean `8e63d87`
  (`us_strategy_backtest_20260911_092937.json`, git_commit + dirty_tree=false),
  figures unchanged: +91.91% / 631 trades / B&H +195.08%.

**Impact on code:**
- `scripts/cron/pyrobot.crontab` — metals + crypto sessions → `--dry-run`.
- `scripts/multi_market_comparison.py`, `scripts/strategy_validation.py` —
  provenance gate (REJECTED → exit non-zero), provenance fields in rows.
- `scripts/strategy_validation.py` — walk_forward available=false + results=null.
- `scripts/weekly_research.py` — always regenerate + provenance gate + exit code.
- `docs/professional_development_standard.md` — §3b.5 corollary.
- `data/reports/multi_market_comparison.json`, `strategy_validation.json` —
  regenerated; `us_strategy_backtest_20260911_092937.json` — new.
