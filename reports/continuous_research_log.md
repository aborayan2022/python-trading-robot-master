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

