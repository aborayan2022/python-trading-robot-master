# Professional Development Standard

**Status:** Ratified 2026-09-06 · **Amended 2026-09-10 (Wave 5 — decision-memo verification procedure)** · **Amended 2026-09-11 (Wave 5 close-out — backtest provenance & clean-tree rule)**
**Applies to:** every feature, fix, or strategy decision in this repository
**Origin:** `reports/بحث_مشاريع_مشابهة_ودروس_مستفادة.md` (2026-09-06)

---

## 1. The Mandatory Rule — "Research Before Building"

> **No new feature is built without first surveying similar projects, references,
> and tools, and extracting their documented pitfalls.**

This is a hard gate, not a suggestion. The project repeatedly discovered that its
"new" architecture already existed in well-known references (e.g. López de Prado's
*Advances in Financial Machine Learning*), and that reinventing those pieces was
net-negative engineering time. Before writing code for any new capability, the
team must:

1. Survey existing open-source implementations and academic/industry references.
2. Extract their documented failures and pitfalls.
3. Compare each pitfall against *our* use case and current code.
4. Write the lesson into `reports/continuous_research_log.md`.
5. Link the lesson to a quality gate or test before implementation is accepted.

A feature that reaches code review without a research-log entry returns to the
author. Exceptions require the explicit sign-off of the technical owner.

## 2. Process

```
Multi-source research
      │
      ▼
Pitfall extraction
      │
      ▼
Comparison with our use case
      │
      ▼
Lesson documentation (continuous research log)
      │
      ▼
Link to quality gates / tests / task list
```

Each step produces an artifact:

| Step | Artifact |
|---|---|
| Research | Sources list with URLs / citations |
| Pitfalls | Numbered list of failure modes found |
| Comparison | Explicit "ours vs. theirs" matrix |
| Documentation | New entry in `reports/continuous_research_log.md` |
| Enforcement | New/changed `pytest` test or a quality gate in CI |

## 3. Recurring Checklist — The Seven Documented Pitfalls

The independent literature on automated-trading failures is consistent; ~70–80% of
retail automated-trading projects fail to produce sustainable returns. Every
release must be reviewed against these seven failure modes before sign-off:

| # | Pitfall | Definition | Our current status (verify each release) |
|---|---|---|---|
| 1 | **Overfitting** | Fitting noise; dazzling in-sample numbers | ✅ Economic gate rejects decorated models; re-check per model release |
| 2 | **Look-ahead bias** | Training/evaluation uses the future | ✅ Next-bar execution; no future look at strategy level — re-check per backtest |
| 3 | **Transaction costs** | Ignoring commissions, slippage, market impact | ✅ Mandatory `ExecutionCostModel` — re-verify with live fills |
| 4 | **Weak risk management** | No stop, no position limits, no circuit breakers | ✅ Kill switch + circuit breaker exist — **re-test under live pressure** |
| 5 | **Data quality** | Garbage/buggy/stale data | ⚠️ yfinance is experiment-only; production uses Alpaca — verify the source per market |
| 6 | **Insufficient forward testing** | Shipping before real paper/live evidence | ⏳ Paper-trading acceptance period now running — see `docs/production_runbook.md` |
| 7 | **Unrealistic expectations** | Expecting instant, automatic profit | ✅ Honest reporting of no-baseline-beating results on record |

**Gate:** a release cannot be tagged without an explicit row-by-row review of this
table for the affected components.

## 3a. Decision-Memo Verification Procedure (added Wave 5)

A decision memo (format per §9 of the multi-market wave order, saved as
`reports/decision_memo_<market>.md` and mirrored into
`reports/continuous_research_log.md`) is **mandatory before any implementation**
for a new market, strategy family, or execution-layer change. Verification:

1. **Order:** the memo must exist and be APPROVED **before** implementation code
   lands. A memo written after its implementation is a **sequence breach**.
2. **Post-hoc handling:** if a breach is discovered (as in Wave 5 — metals and
   crypto memos written after Wave 1), the memo MUST carry a `Post-hoc
   Acknowledgment` section stating the breach explicitly and extracting lessons
   learned. Suppressing the breach is a release blocker.
3. **Content:** the memo must cover the eight §9 fields (why / data source /
   trading calendar / expected strategies / benchmark / risks / cost model /
   decision).
4. **Linkage:** every memo is referenced from the research log; acceptance items
   (`git diff`) for the market must be traceable to a memo entry.
5. **Freshness:** the memo's risk and benchmark sections must still match reality
   at release time (Wave 5 revalidation showed the metal/crypto benchmark
   numbers drifting from the pre-implementation estimates — re-verify).

## 3b. Backtest Provenance & Clean-Tree Rule (added Wave 5 close-out)

Every backtest report must be reproducible from the exact code that generated it.
The 2026-09-10 incident — advisory figures produced from an in-flight working tree
that did NOT reproduce from the committed code — made this a hard rule:

1. **Provenance fields:** every report written by `MultiMarketBacktest` (and the
   standalone `us_strategy_backtest.py`) records a `provenance` object with
   `git_commit` (HEAD SHA) and `dirty_tree` (True when any tracked files are
   modified or untracked non-ignored files exist at run time). A report without
   a SHA, or with `dirty_tree: true`, is **not** a release candidate.
2. **Clean tree before claims:** no report generation, comparison, validation, or
   "clean-tree" statement while uncommitted code changes exist in the working
   tree. Either commit the changes or stash them first. Re-run and re-record
   *after* the final commit; never backfill numbers from a pre-commit tree.
3. **Reproducibility check:** a claimed result should be reproducible by running
   the report file's own script from the recorded commit
   (`git checkout <git_commit> && python backtest_<market>.py`).
4. **Telemetry is untracked:** `data/audit/ledger.jsonl` and
   `data/metrics/runtime_metrics.jsonl` are live session artifacts (always
   appended by smoke/run) and are git-ignored, so they can never make the tree
   appear dirty.

## 4. Approved Reference Library

These are the sanctioned sources the team compares against. New tools should be
added to the library (not silently used) via a research-log entry.

| Reference | Purpose | When to consult |
|---|---|---|
| **AFML** — López de Prado (2018) | Labeling (Triple-Barrier), CV (purged/embargoed, CPCV), backtest design | Any new labeling, CV, or backtest work |
| **mlfinlab** (Hudson & Thames) | Reference implementation of AFML concepts | Sanity-checking our math (parity tests) |
| **NautilusTrader** | Production multi-asset execution engine (Rust/Python) | Any new-market or execution-layer decision |
| **Qlib** (Microsoft) | Quant research/ML pipeline structure | Pipeline architecture comparison |
| **FinRL** | RL-based trading | Only as a future-approach review (not current approach) |
| **TradingAgents / FinRobot** | Multi-agent LLM analysis → execution separation | Any LLM integration decision |
| **backtrader / vectorbt / zipline-reloaded** | Backtest frameworks | Backtest-engine parity checks (cost model, next-bar) |

## 5. Tooling/Approved Practices

- Research findings are documented in the continuous research log before code.
- The weekly research session (Saturdays) scans for updates and reported errors
  in the reference library and updates the log and task list.
- A new market (Egyptian, metals, crypto) or execution-layer change requires the
  NautilusTrader decision memo (Track 3 of the quarterly plan) before any code.

## 6. Recurring Checklists: Where to Run Them

| Checklist | Where it is enforced |
|---|---|
| Seven pitfalls | This document — mandatory before release |
| Research-before-building | This document + `reports/continuous_research_log.md` entry requirement |
| New-market gate | `reports/خطة_التطوير_المهني.md` Track 3 (NautilusTrader memo) |