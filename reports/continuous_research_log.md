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

