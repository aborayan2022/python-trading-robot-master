# AI Trading Consultant Assessment

**Consultant:** Senior Consultant, AI Trading Systems
**Date:** 2026-08-26
**Assessed Project:** `python-trading-robot-master` (consolidated `aborayan2022` fork, August 2026 build)
**Methodology:** Direct source-code read of every new module (`pyrobot/ai/`, `pyrobot/risk/`, `pyrobot/backtesting/`, `pyrobot/runtime/`, `pyrobot/console/`, `pyrobot/features/regime.py`), full test suite live execution (`436 passed`), review of `IMPLEMENTATION_STATUS.md`, and comparison against the mandates in `reports/الرأي_الاستشاري_الصريح_2026-08-22.md`.

---

## 1. Executive Summary

**One-line verdict:** Every engineering mandate from the 2026-08-22 consultant report has been delivered and verified — the project is now a genuine paper-trading platform — but new ML-methodology gaps (uncalibrated probabilities feeding real sizing decisions, label-overlap risk, no economic approval gate) must be fixed before signals can be trusted with capital.

The transformation since 2026-08-22 is substantial: 276 → 436 tests, a fully connected `TradingPipeline`, honest naming, a real walk-forward validator, an isotonic calibrator, PSI wired to position sizing, a management console with RBAC, and a 4-gate live-unlock safety protocol. This is now well above average for open-source trading systems in engineering quality.

The bottleneck has shifted from **engineering** to **evidence of alpha**. The AI layer produces probabilities that flow into sizing and entry decisions, yet those probabilities are uncalibrated at inference time, the approval gate measures accuracy not economics, and the champion artifact is refit on all data without OOS evaluation as a whole. These are not blocking bugs — they are methodology gaps that, if left unfixed, will produce confident-but-possibly-wrong positions with real money.

---

## 2. Compliance Audit: Prior Mandates

Every mandate from `reports/الرأي_الاستشاري_الصريح_2026-08-22.md` §6 (P0 → P3) verified against current code:

| Mandate | Status | Evidence |
|---|:---:|---|
| **P0.1** End-to-end connected pipeline | ✅ | `pyrobot/runtime/pipeline.py:68` — `TradingPipeline.process_bar()` wires Data → Features → Signal → Risk → Execution → Audit → Portfolio. Tested in `tests/test_runtime.py` (11 tests) |
| **P0.2** Main trading loop with heartbeat/shutdown/paper default | ✅ | `pyrobot/runtime/loop.py:92` — `TradingLoop`: SIGINT/SIGTERM handlers, heartbeat logging, `build_alpaca_pipeline(profile="alpaca_paper")` at line 253 |
| **P0.3** Critical safety fixes (sell direction, PaperBroker short, broker bypass) | ✅ | `risk/exposure.py` sell-direction corrected; `paper_broker.py` full short ledger with borrowing; `robot.py` all orders via `broker.place_order` |
| **P0.4** `cancel_order` on broker interface + adapters | ✅ | `BrokerInterface.cancel_order` (abstract) + 4 adapters + `ExecutionEngine.cancel_order` with CANCEL_PENDING→CANCELLED state machine |
| **P0.5** Persistent audit ledger (reload from disk, tamper detection) | ✅ | `audit/ledger.py:140` — JSONL persistence, SHA-256 hash chain, `AuditIntegrityError` on tamper, `verify_file_integrity()` |
| **P1.1** Next-bar execution (no lookahead) | ✅ | `backtesting/engine.py:275` — signal from bar `t` filled at bar `t+1` open. Tests: `test_next_bar_execution`, `test_strategy_sees_only_past_rows` |
| **P1.2** Cost model connected to engine | ✅ | `backtesting/cost_model.py:22` — `ExecutionCostModel` active in engine pipeline (half-spread, volatility slippage, Almgren-Chriss impact, partial fills) |
| **P1.3** Gap handling + intrabar stops | ✅ | `backtesting/engine.py:429-495` — exit at `min(open, stop)` on gap; stop takes priority on tie. Tests: `test_stop_loss_gap_through_open` |
| **P1.4** Unified metrics + `periods_per_year` from bar type | ✅ | `backtesting/metrics.py` — Sharpe annualized by `periods_per_year` derived from bar frequency |
| **P1.5** True walk-forward (retrain per fold, aggregated OOS) | ✅ | `backtesting/walk_forward.py:116` — `run_walk_forward()`: model-agnostic, retrain per fold, concatenated OOS score. Called from `training.py:192` |
| **P1.6** Honest Monte Carlo (seeded RNG, correct counting) | ✅ | Verified in test suite — `default_rng` seeded, double-counting fixed |
| **P1.7** Behavioral smoke tests replaced | ✅ | Tests verify: commissions reduce returns, small size → partial fills, no execution on last bar |
| **P2.1** Label builder (forward returns, multi-horizon, triple-barrier) | ✅ | `ai/labels.py:17` — `LabelBuilder`: `forward_returns()`, `direction_labels()`, `triple_barrier_labels()` with ATR-from-past-only |
| **P2.2** Honest model naming (logistic, not GBDT) | ✅ | `ai/models.py:60` — `LogisticDirectionModel`; alias `GBDTDirectionClassifier` at line 183 with docstring acknowledging the misnomer |
| **P2.3** Honest ensemble naming + exit signals | ✅ | `ai/ensemble.py:35` — `EnsembleSignalEngine` docstring says "single explicit threshold"; exit signals: SELL (line 156), BUY_TO_COVER (line 162) via `position_state` |
| **P2.4** Registry saves artifacts (npz + SHA-256) | ✅ | `ai/registry.py:139` — `register_model()` writes `.npz`, computes SHA-256 at line 162, verified on load at line 192 |
| **P2.5** Drift (PSI) wired to position sizing | ✅ | `runtime/pipeline.py:388-423` — `_run_drift_check()` feeds PSI → `_DRIFT_SCALE` → `RiskManager.set_model_risk_scale()` (1.0/0.75/0.25) |
| **P2.6** Champion auto-load from registry | ✅ | `ai/ensemble.py:61-91` — lazy `_ensure_models_loaded()` fetches champion from `ModelRegistry.get_champion()` |
| **P2.7** Console (supervisor + RBAC + API + web UI) | ✅ | `console/supervisor.py:36` (6 states), `auth.py:32` (3 roles, HMAC, 4-gate live unlock), `api.py` (20 endpoints), `static/` (537 HTML + 907 JS + 956 CSS) |
| **P3** Live trading prerequisites | ⏳ | Paper trading ready; websocket streaming, position reconciliation, TWAP, 3-6 month paper journal pending |

**Result: 17/18 mandates verified ✅; P3 correctly deferred ⏳.**

---

## 3. New Technical Findings

### F1 — CRITICAL: Calibrator Fitted but Never Applied at Inference

**Location:** `pyrobot/ai/training.py:211` (fit) vs. `pyrobot/ai/ensemble.py:140` (inference)

**The bug:** `IsotonicCalibrator` is fitted on in-sample predictions during training:

```python
# training.py:208-212
fitted = model_factory()
fitted.fit(clean, labels)
proba = fitted.predict_proba(clean)[:, 1]
calibrator = IsotonicCalibrator().fit(proba, labels)
calibration = calibrator.report(proba, labels)
```

The calibrator is then discarded — never serialized to `.npz`, never stored in the registry, never loaded by the ensemble. At inference, `ensemble.py:140` uses raw `predict_proba`:

```python
# ensemble.py:140
probs = self.direction_model.predict_proba(features_df.iloc[[-1]])
prob_up = float(probs[0, 1])
```

**Impact:** The `min_probability=0.80` entry threshold (`ensemble.py:44,170`) operates on uncalibrated logistic regression probabilities. Logistic regression probabilities are often well-calibrated in aggregate but can be miscalibrated in specific regions (e.g., extreme tails, regime-shifted data). The `max_calibration_error=0.15` gate (`training.py:29,217`) evaluates calibration on training data but the deployed model ignores it entirely. Entry/exit decisions and Kelly sizing confidence are all based on raw probabilities.

**Acceptance criteria:**
1. `IsotonicCalibrator` fitted during training must be serialized alongside the model artifact.
2. `EnsembleSignalEngine` must load and apply the calibrator before threshold comparison.
3. A test must assert that `calibrator.transform(raw_proba)` is called during `generate_signal()`.

---

### F2 — HIGH: Label Leakage Risk from Insufficient Purging

**Location:** `pyrobot/ai/training.py:199-203`

```python
result = run_walk_forward(
    clean, labels,
    ...
    embargo_days=1,
    ...
)
```

The walk-forward validator (`walk_forward.py:67`) inserts a 1-day embargo gap between train and test windows. However, the labels use `horizon=5` (line 171), meaning each label at time `t` depends on bars `t+1` through `t+5`. An embargo of 1 day is insufficient: a sample in the test set at `t_test_start` can have its label influenced by a bar at `t_test_start + 4`, which falls within the same calendar week as the last training sample at `t_train_end + 1`.

The walk-forward validator (`walk_forward.py:81-82`) uses calendar-date masks, not bar-level purging. With minute-bar data, 1 calendar day ≈ 390 bars. With daily data, 1 calendar day = 1 bar. Neither case provides purging of label-overlapping rows — the embargo only separates training and test *indices*, but the labels themselves span beyond that gap.

**Impact:** Optimistic OOS accuracy estimates. The model may appear to generalize better than it does, leading to false confidence in signal quality.

**Acceptance criteria:**
1. Embargo must be at least `horizon` bars (not days) when working with intraday data, OR
2. Explicit purging must remove training rows whose labels overlap with test-set timestamps.

---

### F3 — HIGH: Calibration Gate Uses In-Sample Predictions

**Location:** `pyrobot/ai/training.py:209-212`

```python
fitted = model_factory()
fitted.fit(clean, labels)
proba = fitted.predict_proba(clean)[:, 1]
calibrator = IsotonicCalibrator().fit(proba, labels)
calibration = calibrator.report(proba, labels)
```

After walk-forward OOS evaluation, the model is refit on ALL data (`clean`, line 209) and the calibration error is measured on those same training predictions. The `max_calibration_error=0.15` gate (`training.py:217`) then passes or fails based on this in-sample ECE.

**Impact:** In-sample ECE is systematically optimistic. The gate can pass spuriously, allowing a champion candidate with genuinely poor calibration into challenger status. Combined with F1 (calibrator not applied at inference), this means: (a) the gate may be too lenient, and (b) even when it passes, the calibrator is discarded.

**Acceptance criteria:**
1. Calibration ECE must be computed from OOS predictions (aggregated across walk-forward folds), not from the refit-on-all-data model.
2. Alternatively, a held-out calibration set must be held out from the walk-forward entirely.

---

### F4 — HIGH: Approval Gate Measures Accuracy, Not Economics

**Location:** `pyrobot/ai/training.py:214-218`

```python
approved = (
    len(result.oos_predictions) >= gate.min_oos_samples
    and result.oos_score >= max(bh, sma) + gate.min_oos_accuracy_edge
    and calibration["expected_calibration_error"] <= gate.max_calibration_error
)
```

And `pyrobot/ai/registry.py:253-257` (champion promotion gate):

```python
baseline = max(meta.oos_metrics["buy_hold_accuracy"], meta.oos_metrics["sma_accuracy"])
if meta.oos_metrics["oos_accuracy"] <= baseline:
    raise ModelNotApprovedError(...)
```

**The gaps:**
- The gate requires `oos_accuracy > baseline + 1%`. This measures classification accuracy, not PnL. A model can be 51% accurate and profitable, or 60% accurate and unprofitable (if wrong on large moves).
- No cost-aware OOS PnL gate: backtested returns minus costs are never compared against a minimum Sharpe, profit factor, or max drawdown.
- No multiple-testing correction: with 3 walk-forward folds, the probability of at least one fold spuriously beating the baseline by chance is non-trivial. No PBO (Probability of Backtest Overfitting) or deflated Sharpe adjustment is applied.
- No minimum win/loss ratio or expected-value gate.

**Impact:** A model can become champion by being slightly more accurate than buy-and-hold while generating negative expected returns after costs. The system will then trade it with real sizing.

**Acceptance criteria:**
1. Add an OOS PnL gate: `total_oos_pnl - total_costs > min_profit_threshold` or `oos_sharpe > min_sharpe`.
2. Add a minimum expected value gate: `E[profit_per_trade] > 0` after cost model.
3. Consider PBO or deflated Sharpe for multiple-fold evaluation.

---

### F5 — MEDIUM: Champion Artifact Refit on All Data Without Whole-Model OOS

**Location:** `pyrobot/ai/training.py:208-209`

```python
fitted = model_factory()
fitted.fit(clean, labels)
```

After walk-forward evaluation, the champion candidate is trained on ALL available data. The metadata records OOS metrics from walk-forward folds (line 229-235), but the registered artifact is the refit-on-all model — a model that has never been evaluated as a whole on truly unseen data.

**Impact:** The deployed model (refit on all data) may perform differently from the walk-forward OOS estimate, especially if the data distribution is non-stationary. This is standard practice in production ML, but it means the OOS metrics are estimates, not guarantees, for the champion artifact specifically.

**Acceptance criteria:**
1. Document this explicitly in `ModelMetadata.description` (partially done at line 237).
2. Add a shadow-validation step: after refit, evaluate on the most recent N bars (held out from both train and walk-forward) as a final sanity check.

---

### F6 — MEDIUM: `fastapi` Not in Default Dependencies

**Location:** `pyproject.toml` (core dependencies vs. optional groups)

The core `dependencies` list contains only `pandas`, `numpy`, and `python-dotenv`. `fastapi>=0.110` and `uvicorn>=0.29` are declared under `[project.optional-dependencies]` in the `console` and `dev` groups but not in the default install.

**Impact:** In a clean `pip install .` environment, 15 console integration tests (`tests/test_console.py`) fail with `ModuleNotFoundError: No module named 'fastapi'`. The test suite reports 436 collected but only 421 pass in the default environment.

**Acceptance criteria:**
1. Add `fastapi` and `uvicorn` to the core dependencies, OR
2. Add a pytest marker (`@pytest.mark.console`) and skip those tests when fastapi is unavailable, OR
3. Document the install command (`pip install -e ".[console]"`) prominently in README and CI.

---

### F7 — MEDIUM: Sizing Confidence Derived from Uncalibrated Probability

**Location:** `pyrobot/ai/ensemble.py:150` and `pyrobot/risk/position_sizer.py:101`

```python
# ensemble.py:150
confidence = float(abs(prob_up - 0.5) * 2.0)
```

```python
# position_sizer.py:101
adjusted_f = kelly_f * self._kelly_fraction * confidence
```

The `confidence` metric fed into Kelly/fixed-fraction sizing is a linear rescale of raw (uncalibrated) `prob_up`. If `prob_up=0.85`, confidence = 0.70. This directly scales the Kelly fraction and thus the dollar amount risked per trade.

**Impact:** Combined with F1, sizing decisions are based on potentially miscalibrated probabilities. If the model's true P(up) is 0.70 but reports 0.85 (uncalibrated), the system will over-size positions by ~30% relative to the true edge.

**Acceptance criteria:**
1. Resolves automatically when F1 is fixed (calibrator applied before confidence calculation).
2. As a standalone check: confidence should never feed directly into Kelly without calibration — Kelly itself requires accurate `win_rate` input.

---

### F8 — INFO: Naming Honesty (Single-Model "Ensemble")

**Location:** `pyrobot/ai/ensemble.py:35`

The class is named `EnsembleSignalEngine` but contains exactly one direction model and one volatility model (lines 41-42). This is functionally a two-model pipeline, not an ensemble in the ML sense (no bagging, boosting, stacking, or blending). The docstring at line 1 acknowledges "model forecasts" (plural) but the name implies a statistical ensemble.

**Status:** This is acceptable for a v1 — the prior report's naming concerns have been largely addressed (GBDT→Logistic, LLM→Lexicon). The "ensemble" name is a minor overclaim but not misleading given the docstring.

---

### F9 — INFO: Simple V1 Regime Detector

**Location:** `pyrobot/features/regime.py:33`

`MarketRegimeDetector` uses SMA crossover + volatility percentile with hard-coded thresholds (lines 99-113):
- CRISIS: `vol_pct >= 0.95 AND trend < -0.05`
- HIGH_VOL: `vol_pct >= 0.85`
- BULL: `trend > 0.02`
- BEAR: `trend < -0.02`
- SIDEWAYS: else

**Status:** Appropriate for v1. The thresholds are reasonable starting points but would benefit from backtesting-derived optimization or adaptive calibration in future iterations.

---

### F10 — INFO: Legacy Technical Debt and Zero Live Fills

**Legacy debt:** ~120 mypy errors concentrated in pre-existing files (`robot.py`, `trades.py`, `brokers/`). The newly written core modules (`runtime/`, `ai/`, `risk/`, `audit/`, `backtesting/`, `execution/`, `features/`) are clean.

**Smoke test result:** The Alpaca smoke test (`tests/test_alpaca_production.py`) confirmed correct fail-safe behavior — `KILL_SWITCH_TRIGGERED` on stale data outside market session. Zero live fills observed (expected during automated testing outside market hours).

---

## 4. Readiness Matrix

| Dimension | Score | Details |
|---|:---:|---|
| **Core Trading Engine** | **100%** | `TradingPipeline` + `TradingLoop` fully connected, tested (11 runtime tests), operational |
| **Backtesting Honesty** | **100%** | Next-bar execution, no lookahead, cost model connected, gap handling, walk-forward retrain |
| **AI Layer** | **~85%** | Labels ✅, models ✅, registry ✅, drift ✅; calibration fitted-but-not-applied (F1), in-sample ECE gate (F3), no economic gate (F4) |
| **Risk Management** | **~95%** | Kill switch, circuit breaker, position sizer, exposure monitor all solid; sizing confidence derives from uncalibrated probability (F7, resolved by F1) |
| **Console / Operations** | **~95%** | Supervisor, RBAC, 20 endpoints, SSE, bilingual UI all code-complete; 15 tests blocked by optional dep (F6); no manual QA reported |
| **Live Trading Readiness** | **~60%** | Alpaca paper broker integrated, 4-gate live unlock designed; requires: paper evidence period, F1-F4 fixes, websocket streaming |

---

## 5. Prioritized Roadmap

### R0 — Correctness Fixes (1-2 days)

These are methodology bugs that produce wrong results today.

| ID | Fix | Acceptance Test |
|---|---|---|
| F1 | Serialize calibrator in `register_model()`, load in `EnsembleSignalEngine`, apply before threshold. | Test: `generate_signal()` output changes when calibrator is present vs. absent |
| F3 | Compute ECE from OOS predictions (aggregate walk-forward fold predictions), not from refit-on-all. | Test: `calibration["expected_calibration_error"]` differs between in-sample and OOS |
| F2 | Increase embargo to `horizon` bars OR add explicit label purging. | Test: no training sample's label window overlaps any test sample's timestamp range |
| F6 | Add `pytest.importorskip("fastapi")` marker to console tests. | Test: `pytest tests/` passes 436/436 in clean env without `[console]` extra |

### R1 — Economic Validation Gate (2-3 weeks)

Without this, the system can approve unprofitable models.

| ID | Fix | Acceptance Test |
|---|---|---|
| F4a | Add OOS PnL gate: `total_oos_pnl - total_costs > 0` | Test: model with positive accuracy but negative PnL is rejected |
| F4b | Add expected-value gate: `E[profit_per_trade] > commission + slippage` | Test: marginal-accuracy model is rejected |
| F4c | Add deflated Sharpe or PBO estimate for multi-fold evaluation | Test: model passing 1/3 folds but failing 2/3 is flagged |
| F5 | Shadow validation: after refit-on-all, evaluate on final 10% held-out data | Test: shadow OOS metrics recorded in metadata |

### R2 — Real-Data ML Baseline + LightGBM (1-2 months)

| ID | Fix | Acceptance Test |
|---|---|---|
| — | Train `LogisticDirectionModel` on real Alpaca historical data via `run_walk_forward` | OOS accuracy > buy-and-hold + 1% on real data |
| — | Implement `OptionalLightGBMDirectionModel.save()`/`load()` with joblib persistence | Test: round-trip save/load produces identical predictions |
| — | Persist calibrator alongside model artifact in registry | Test: loaded champion's calibrator transforms identically to fresh fit |
| — | Evaluate LightGBM vs. Logistic via walk-forward on same data | Comparison report: accuracy, calibration, PnL |

### R3 — Paper Trading Evidence Period (3-6 months, mandatory)

Before any live-unlock review:

1. Run on Alpaca Paper Trading for minimum 3 months with daily logging.
2. Document: total trades, win rate, average PnL per trade, max drawdown, Sharpe ratio, calibration drift.
3. Compare paper results against walk-forward OOS estimates.
4. Only then: review for live-unlock (which already requires the 4-gate safety protocol in `auth.py:159-238`).

---

## 6. Final Verdict

> **The engineering is now above average for open-source trading systems. The bottleneck has shifted from engineering to evidence of alpha.**

The project has transformed from a disconnected collection of well-built components (the 2026-08-22 verdict: "3/10 as a trading platform, 6.5/10 as engineering foundation") into a genuinely connected, tested, auditable paper-trading system. The 2026-08-22 mandates were delivered faithfully and verified in this review.

However, the AI layer — now the last mile before real money — has methodology gaps that are invisible in accuracy metrics but visible in economic outcomes. Uncalibrated probabilities feeding Kelly sizing, an approval gate that ignores costs, and an embargo shorter than the label horizon are the kind of issues that don't appear in unit tests but appear in account statements.

**Do not trade real money until:**
1. R0 fixes are merged and tested (calibration at inference, OOS ECE, embargo, fastapi).
2. R1 economic gates are implemented and validated against known-good and known-bad models.
3. R3 paper trading period (minimum 3 months) is completed with documented evidence.

**Current production readiness: 7/10 for paper trading. 4/10 for live trading (pending R0-R3).**

---

*This report continues the series after `reports/الرأي_الاستشاري_الصريح_2026-08-22.md`. All file:line citations verified by direct source read on 2026-08-26.*
