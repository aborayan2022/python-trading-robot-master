# Consultant Response & Execution Directive

**From:** Senior Consultant, AI Trading Systems
**To:** python-trading-robot Development Team
**Date:** 2026-08-26
**Subject:** Response to your delivered report `AI_Trading_Consultant_Assessment_2026-08-26.md` — accepted, with one precision correction — and the binding work orders to close findings F1–F7.

---

## 1. Verification of Your Report — ACCEPTED

I independently re-audited the citations in your delivered report against the source tree before issuing this directive:

| Your claim | My verification | Result |
|---|---|---|
| Champion gate is accuracy-based at `registry.py:253-257` | Read directly — `baseline = max(buy_hold, sma); if oos_accuracy <= baseline: raise` | ✅ Accurate |
| `fastapi`/`uvicorn` only in optional groups | `pyproject.toml:34-46` — core deps are `pandas/numpy/python-dotenv` only; `fastapi` under `console` and `dev` | ✅ Accurate |
| Calibrator discarded after training | `IsotonicCalibrator` has **no** `save()`/`load()` at all (`calibration.py` — only `fit`/`transform`/`report` exist); never referenced by `ensemble.py` | ✅ Accurate |
| 20 API endpoints | `grep -c "@router\." api.py` → 20 | ✅ Accurate |
| Embargo 1 day vs horizon 5 | `training.py:200-203` (`embargo_days=1`) vs `horizon=5` default at line 171 | ✅ Accurate |

**One precision correction — F7:** Your report states sizing confidence feeds Kelly. In the **live runtime path** the pipeline calls `calculate_position_size(..., method="fixed_fraction")` with placeholder Kelly arguments (`win_rate=0.0, avg_win=0.0, avg_loss=0.0` — `runtime/pipeline.py:327-335`). Kelly is reachable via the API surface but is not the runtime default. **The material risk stands unchanged**: `confidence = max(0.05, signal.confidence)` still linearly scales `risk_per_trade_pct`, so uncalibrated probability still directly scales position size. The root cure remains WO-1; WO-7 covers the cleanup.

Your report is accepted as the factual baseline. What follows converts findings into merge-ready work orders with binding acceptance tests. No work order is "done" until its acceptance test exists in `tests/` and passes.

---

## 2. Sequencing Rule (Read First)

**The R3 paper-trading evidence clock starts ONLY after WO-1 through WO-4 are merged.** Paper results produced by an uncalibrated threshold system are evidence about the wrong system and will not count toward the live-unlock review.

Dependency chain: WO-2 and WO-3 fix the evaluation itself → WO-1 deploys correct inference → WO-4 installs the economic gate → WO-5 validates the whole artifact → only then retrain the champion candidate and start the paper journal.

---

## 3. Work Orders

### WO-6 — Make the test suite install-honest (F6) — **Day 1, ~1 hour, no dependencies**

**Files:** `tests/test_console.py`, `README.md`, `.github/workflows/ci.yml` (if present)

**Steps:**
1. Add at the top of `tests/test_console.py`, before any fastapi import:
   ```python
   fastapi = pytest.importorskip("fastapi")
   ```
2. README: add a one-line install matrix — `pip install .` (core + 421 tests) vs `pip install ".[console]"` (full 436).
3. CI: ensure the primary job installs `.[console,dev]`; optionally add one bare-install job to keep the split honest.

**Acceptance test:** In a clean venv with bare `pip install .`: `pytest tests/` collects and passes 421 with **zero collection errors**. With `.[console]`: 436 pass.

---

### WO-2 — Purge label overlap in walk-forward (F2) — **Week 1, ~1-2 days**

**Files:** `pyrobot/backtesting/walk_forward.py`, `pyrobot/ai/training.py`, `tests/test_walk_forward.py` (or nearest existing)

**Steps:**
1. Extend `WalkForwardValidator.split()` with a `purge_bars: int = 0` parameter: after computing `train_idx`, drop every training row whose timestamp is within `purge_bars` of `test_start` (i.e., `t_train > t_test_start - purge_bars` is removed). Purge by **bar count**, not calendar days — `walk_forward.py:81-82` currently masks by calendar date, which conflates 1 day with 390 minute-bars.
2. Thread `purge_bars` through `run_walk_forward()`.
3. In `training.py:192-204`, pass `purge_bars=horizon` (the label horizon) and keep `embargo_days=1` as a calendar-floor safety on top.
4. Docstring: state the rule "purge ≥ label horizon" as an invariant, so future horizons can't silently violate it.

**Acceptance tests:**
1. `test_no_label_overlap_across_folds`: synthetic minute-bar frame, `horizon=5`; assert no training timestamp lies in `(test_start - 5 bars, test_start)`.
2. `test_purge_prevents_leak_inflation`: build a synthetic dataset with a leak-prone pattern (e.g., label = sign of next-bar return, feature = current return with planted partial correlation); assert OOS score with `purge_bars=horizon` is measurably lower than with `purge_bars=0`.
3. On pure noise data: OOS accuracy ≈ 50% ± noise band, with the test asserting the confidence interval contains 0.5.

---

### WO-3 — Calibrate and gate on OOS predictions (F3) — **Week 1, ~1-2 days, after WO-2**

**Files:** `pyrobot/backtesting/walk_forward.py`, `pyrobot/ai/training.py`, `tests/test_model_training_governance.py`

**Steps:**
1. Extend `run_walk_forward()` to optionally collect probabilities: add `proba_fn: Optional[Callable[[Any, pd.DataFrame], np.ndarray]] = None`; when provided, aggregate `oos_probabilities` alongside `oos_predictions` (same concatenation pattern, `walk_forward.py:179-182`). Accuracy still uses thresholded `predict_fn` output.
2. In `train_direction_champion_candidate()` (`training.py`):
   - Pass `proba_fn=lambda m, x: m.predict_proba(x)[:, 1]`.
   - Fit the calibrator on **`(result.oos_probabilities, result.oos_labels)`** — never on in-sample predictions.
   - Compute `calibration = calibrator.report(result.oos_probabilities, result.oos_labels)` so the `max_calibration_error=0.15` gate (`training.py:217`) evaluates OOS ECE.
   - Keep the in-sample ECE only as a diagnostic field if desired — it must not gate anything.
3. Record both in the report dict: `calibration_oos` (governing) and optionally `calibration_insample_diagnostic`.

**Acceptance tests:**
1. `test_ece_gate_uses_oos_predictions`: with a deliberately overconfident synthetic model (e.g., probabilities pushed toward 0/1 by a temperature < 1), in-sample ECE after isotonic fitting is near zero while OOS ECE remains material — assert the gate reads the OOS number.
2. `test_gate_rejects_overconfident_model`: the same setup must produce `approved_for_challenger == False` under the OOS gate where it would have passed under the in-sample gate.

---

### WO-1 — Persist the calibrator and apply it at inference (F1) — **Week 1-2, ~2-3 days, after WO-3**

This is the critical fix. Everything upstream (WO-2/WO-3) exists so that the calibrator deployed here is worth deploying.

**Files:** `pyrobot/ai/calibration.py`, `pyrobot/ai/registry.py`, `pyrobot/ai/training.py`, `pyrobot/ai/ensemble.py`, `tests/test_ai_platform.py`

**Steps:**
1. `IsotonicCalibrator.save(path)` / `load(path)` — serialize `thresholds_` and `values_` to `.npz` with `allow_pickle=False`, mirroring the artifact pattern in `ai/models.py:148-178`. Include an `is_fitted` flag; `load()` raises on an unfitted file.
2. `ModelMetadata`: add optional `calibration_path: Optional[str]` and `calibration_sha256: Optional[str]`.
3. `ModelRegistry.register_model(metadata, model, calibrator=None)`: when a calibrator is given, persist it next to the model artifact as `{artifact_stem}.calib.npz`, record path + SHA-256 in metadata. `load_model()` (or a new `load_calibrator(model_id, version)`) verifies the SHA-256 before returning — same integrity contract as the model artifact (`registry.py:139-192`).
4. `training.py`: register the OOS-fitted calibrator from WO-3 together with the model.
5. `EnsembleSignalEngine`:
   - `_ensure_models_loaded()` (`ensemble.py:61-91`): also load the calibrator when present.
   - `generate_signal()` (`ensemble.py:139-141`): transform before any use:
     ```python
     probs = self.direction_model.predict_proba(features_df.iloc[[-1]])
     prob_up = float(probs[0, 1])
     if self.calibrator is not None:
         prob_up = float(self.calibrator.transform(np.array([prob_up]))[0])
     ```
   - Every downstream consumer (threshold 0.80/0.45, confidence, `expected_return`) now operates on the calibrated value. No other change needed — that single insertion point is the design's advantage.
   - Absence of a calibrator must remain a **loud warning log at load time** (`"champion loaded WITHOUT calibrator — thresholds operate on uncalibrated probabilities"`), not a silent pass.

**Acceptance tests:**
1. `test_signal_changes_with_calibrator`: fit a model + a calibrator that materially shifts the operating region; assert `generate_signal()` output differs between calibrator-present and calibrator-absent engines on the same features.
2. `test_calibrator_registry_round_trip`: register model+calibrator, load in a fresh engine, assert `transform()` output identical to the pre-serialization fit.
3. `test_calibrator_tamper_detected`: modify one byte of the `.calib.npz` file; assert loading raises `ArtifactIntegrityError`.
4. `test_threshold_sees_calibrated_probability`: construct a case where raw `p=0.82` but calibrated `p=0.74`; assert NO_TRADE (below the 0.80 threshold).

**Definition of done (grep-level):** with a champion that has a calibrator registered, there is no code path from `predict_proba` to the `min_probability` comparison that skips `transform`.

---

### WO-4 — Economic approval gate (F4) — **Weeks 2-3, ~3-5 days, after WO-1 + WO-3**

**Files:** new `pyrobot/ai/economic_gate.py` (or extension of `training.py`), `pyrobot/ai/registry.py:230-261`, `pyrobot/ai/training.py`, tests

**Steps:**
1. Build `evaluate_oos_economics(oos_probabilities, oos_labels, aligned_prices, ...)`:
   - Reconstruct the signal sequence the **deployed engine** would have produced: apply the calibrated entry threshold (`prob >= 0.80` long entry in BULL/SIDEWAYS; `prob <= 0.20` short entry in BEAR/HIGH_VOL) and the exit threshold (0.45) to the OOS probability stream, using per-symbol price frames for regime context.
   - Replay those signals through the existing honest backtester — next-bar execution + `ExecutionCostModel` (`backtesting/engine.py`, `backtesting/cost_model.py`). Do not write a second execution simulator; reuse the engine, that is what it is for.
   - Output: `net_pnl_after_costs`, `sharpe` (annualized via `periods_per_year` from bar frequency), `max_drawdown`, `profit_factor`, `n_trades`, `ev_per_trade`.
2. `TrainingGateConfig` gains: `min_oos_net_pnl: float = 0.0`, `min_oos_trades: int = 20`, `min_ev_per_trade: float = 0.0`, `min_profit_factor: float = 1.0`. Defaults are deliberately permissive at first; tighten after the first real-data run.
3. Approval condition in `training.py:214-218` gains the economic block; `oos_metrics` records all economic fields.
4. `_validate_champion_candidate()` (`registry.py:241-261`): add the economic metrics to the `required` set and add rejection conditions — negative net PnL, EV per trade ≤ 0, insufficient trades. A model that cannot show economics **cannot be promoted, regardless of accuracy**.
5. Multiple-testing hygiene (may land slightly later but must land): when more than 3 candidate configurations are tried on the same data, run the trial log through a PBO-style assessment or apply a deflated-Sharpe adjustment; at minimum, record `n_trials` in metadata so the review can see how many attempts produced this champion.

**Acceptance tests:**
1. `test_high_accuracy_negative_economics_rejected`: synthetic stream with ~60% directional accuracy but payoff profile that loses after costs (small wins, large losses) → `approved_for_challenger == False`, and the report states economics as the reason.
2. `test_marginal_model_fails_cost_gate`: gross-positive but cost-negative EV → rejected.
3. `test_registry_blocks_promotion_without_economics`: metadata missing economic metrics → `ModelNotApprovedError`.
4. `test_few_trades_not_approved`: all metrics positive but `n_trades < min_oos_trades` → rejected (statistical insignificance guard).

---

### WO-5 — Shadow validation of the deployed artifact (F5) — **Week 3, ~1-2 days, after WO-4**

**Files:** `pyrobot/ai/training.py`, `pyrobot/ai/registry.py`, tests

**Steps:**
1. Reserve the final `test_period_days` (or last 10%, whichever is larger) as a **holdout excluded from the entire walk-forward**.
2. After the refit-on-training-data (`training.py:208-209`), evaluate once on the holdout: accuracy, ECE (calibrated), and — via WO-4 — net economics.
3. Record as `shadow_accuracy`, `shadow_ece`, `shadow_net_pnl` in `oos_metrics`. Extend `ModelMetadata.description` to state explicitly: "Artifact refit on all training data after walk-forward; OOS metrics estimate fold behavior, shadow metrics measure the deployed artifact on untouched data."
4. Soft gate for now: a shadow-vs-OOS degradation beyond a documented tolerance (suggest: accuracy drop > 5 points or shadow net PnL < 0) must flip status to CANDIDATE and require human review rather than auto-CHALLENGER.

**Acceptance test:** `test_shadow_metrics_recorded_and_gating`: craft data where the final segment behaves differently (regime change); assert shadow metrics differ from OOS metrics in metadata, and the degradation path demotes the candidate.

---

### WO-7 — Sizing-confidence cleanup (F7) — **Week 3, ~0.5 day, last**

**Files:** `runtime/pipeline.py:327-335`, `risk/manager.py:279-334`, docstrings

**Steps:**
1. Root cure is WO-1 — once the threshold sees calibrated probabilities, `confidence = |p_cal − 0.5| × 2` is a defensible edge proxy. Verify no sizing path reads raw probability after WO-1 (add an assertion-style test if cheap).
2. `pipeline.py:327-335`: remove the misleading dead arguments (`win_rate=0.0, avg_win=0.0, avg_loss=0.0` are ignored by `fixed_fraction`) — pass only what the chosen method consumes, or split the `calculate_position_size` signature per method.
3. Document the `max(0.05, ...)` confidence floor (`pipeline.py:333`): state why a floor exists (avoids zero-size on valid signals) and that it never applies to NO_TRADE paths.
4. `position_sizer.py` docstring: add "confidence input must be derived from calibrated probabilities (see WO-1); Kelly additionally requires realized win_rate/avg_win/avg_loss from trade history — never placeholders."

**Acceptance test:** `test_sizing_uses_calibrated_confidence`: end-to-end — same features, engine with vs without calibrator produces measurably different position sizes (ties WO-1 and WO-7 together).

---

## 4. Schedule Summary

| Sprint | Work orders | Gate at end of sprint |
|---|---|---|
| **Day 1** | WO-6 | Bare install: 421 pass, no collection errors |
| **Week 1** | WO-2 → WO-3 | Purge tests + OOS-ECE tests green; noise-data OOS ≈ 50% |
| **Week 2** | WO-1 | Signal-path calibration test + tamper test + registry round-trip green |
| **Weeks 2-3** | WO-4 | Economic-gate test battery green; registry blocks economics-free champions |
| **Week 3** | WO-5 → WO-7 | Shadow metrics in metadata; sizing-cleanup test green |
| **Then** | Retrain champion candidate on real Alpaca history under the new gates | **Paper-trading clock (R3, ≥3 months) starts here — not before** |

Total estimated effort: **2-3 focused weeks**. This is small relative to what it protects.

---

## 5. What I Will Verify at the Next Review

1. `pytest tests/` in a bare venv and in `.[console]` — both clean (WO-6).
2. Read the new purge/embargo invariant and run the noise-data check myself (WO-2).
3. Train a candidate on real Alpaca history; open the registry JSON; confirm `calibration_path` + SHA, OOS ECE, and the full economic metric block exist (WO-1/3/4).
4. Tamper one byte of the calibrator artifact; expect `ArtifactIntegrityError` (WO-1).
5. Attempt to promote an economics-free model; expect `ModelNotApprovedError` (WO-4).
6. Check the audit ledger for `MODEL_DRIFT_CHECK` events with the drift scale reflected in subsequent position sizes (existing wiring, must remain intact).
7. Confirm the paper journal start date is **after** the WO-1..4 merge date. Journal entries before that date will be struck from the live-unlock evidence.

---

## 6. Closing Position

Your delivered report was accurate, self-critical, and correctly prioritized — the citation audit above confirms it. That is exactly the standard this project now operates at, and it is why these work orders are precise rather than cautionary.

The system's engineering made it honest about execution. These seven work orders make it honest about **model selection**. After they merge and the paper journal accumulates three months of calibrated, cost-gated evidence, the live-unlock review becomes a reasonable conversation instead of a gamble.

**No real money until: WO-1 through WO-4 merged and tested → champion retrained under the new gates → ≥3 months documented paper trading. This sequence is binding.**

— Senior Consultant, AI Trading Systems
