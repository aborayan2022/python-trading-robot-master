---
name: trading-model-validation
description: "Validate Python algorithmic-trading model work end to end. Use for reviewing ML model integrations, feature changes, console settings, backtests, OOS reports, risk gates, artifact integrity, and release-readiness decisions in a trading robot."
argument-hint: "Describe the model, feature, strategy, or completion report to validate."
user-invocable: true
disable-model-invocation: false
---

# Trading Model Validation

## Purpose

Produce an evidence-based validation result for a trading-model or strategy change. The result must distinguish code completion, statistical signal quality, and economic deployability. A higher accuracy number is never sufficient for approval.

## Safety Rules

- Do not enable live trading, submit broker orders, or weaken a risk gate while validating.
- Prefer offline tests, deterministic fixtures, paper-mode replay, and backtests.
- Treat a missing metric, unavailable dependency, or unverifiable report as an explicit gap, not as a pass.
- Never approve a model for paper or live use solely because unit tests pass.
- Preserve unrelated user changes and keep edits limited to the requested validation or defect.

## Procedure

### 1. Establish the validation target

1. Identify the changed files, owning abstraction, model or strategy entry point, and requested acceptance criteria.
2. Read the nearest tests, configuration, production safety documentation, and existing report before changing code.
3. State one falsifiable hypothesis about the change and one cheap check that could disconfirm it.
4. Check the working tree before editing so unrelated changes are not overwritten.

Record the target as one of:

- implementation correctness;
- model/artifact lifecycle;
- feature correctness and look-ahead safety;
- API or console behavior;
- backtest/OOS evidence;
- release or governance decision.

### 2. Verify implementation contracts

Trace the smallest relevant path from input to output:

`data -> features -> model -> signal -> risk/economic gate -> execution/audit -> report`

Check that:

- public APIs preserve their existing contract unless a change is intentional;
- optional dependencies remain optional and fail clearly when unavailable;
- model registration, factory lookup, save, load, and metadata behavior agree;
- feature calculations use only information available at the decision timestamp;
- calendar calculations use actual index/calendar values rather than fixed assumptions;
- configurable periods and thresholds are read from configuration, not silently hard-coded;
- RBAC, input validation, and reset/update semantics are enforced at the owning boundary;
- audit and risk decisions remain observable and tamper-evident.

If a contract fails, fix the smallest root cause and rerun the focused check before widening scope.

### 3. Test artifact and input integrity

For model persistence, verify all of the following where applicable:

1. A fitted model can save and load with equivalent predictions.
2. An unfitted model is rejected clearly.
3. Missing, malformed, or incompatible artifacts are rejected clearly.
4. Metadata required for reconstruction is contained in the integrity-protected artifact, not only in an unverified sidecar.
5. Registry checksum verification covers every field that affects behavior.
6. Tampering with the artifact is detected before use.
7. Optional model dependencies do not break unrelated core imports or tests.

For API or console configuration, verify:

- authorized roles can read and update settings;
- unauthorized roles are rejected;
- partial updates merge correctly;
- empty bodies, unknown keys, invalid HEX colors, and unsafe URLs are rejected;
- reset restores documented defaults;
- test settings use an isolated temporary path.

### 4. Test feature and data correctness

Use focused tests for normal, boundary, and missing-data cases. Include at least one no-lookahead check when features depend on time series data. For date-sensitive features, cover short and long months, month boundaries, and leap-year behavior where relevant.

For configurable indicators, test a non-default period so a hard-coded default cannot pass unnoticed. Confirm output names, metadata, NaN behavior, index alignment, and registration in the default feature engine.

### 5. Validate statistical and economic evidence

Run the narrowest relevant tests first, then the full suite when practical. Use the repository's configured commands, normally:

```bash
pytest -q tests/test_<target>.py
pytest -q
```

For OOS or backtest evidence, record:

- exact data period, symbols, frequency, and split boundary;
- feature/target horizon and whether all transformations are fit only on training data;
- benchmark such as buy-and-hold or a no-signal baseline;
- accuracy plus class balance and trade count;
- gross and net P&L after commissions, spread, slippage, and financing assumptions;
- expectancy or EV per trade, win rate, turnover, and max drawdown;
- rejected, skipped, or gated trades;
- random seeds, model version, configuration, and artifact checksum.

A model is **not approved** when any of these is true:

- net performance is negative after realistic costs;
- EV per trade is negative or unavailable;
- drawdown or risk limits fail;
- the model does not beat the defined benchmark under the agreed metric;
- the result is in-sample only, leaks future data, or cannot be reproduced;
- required governance or audit evidence is missing.

A model may be a **candidate** when implementation and evidence are sound but economic gates are not met. Candidate status never authorizes paper or live deployment; it requires further validation and an explicit transition to `APPROVED`.

### 6. Decide and report

Use exactly one disposition:

- `APPROVED`: all technical, statistical, economic, reproducibility, and safety gates pass;
- `CANDIDATE`: technically valid but one or more deployment gates fail or remain incomplete;
- `REJECTED`: a correctness, integrity, leakage, safety, or reproducibility defect blocks use.

Report in this order:

1. disposition and one-sentence reason;
2. findings ordered by severity, with file links and test names where available;
3. evidence table comparing model and benchmark;
4. commands run and their results;
5. files changed;
6. remaining risks, missing evidence, and the smallest next action.

Write the report in Arabic by default. Keep code identifiers, file paths, commands, metric names, and disposition labels such as `APPROVED`, `CANDIDATE`, and `REJECTED` unchanged. Use another report language only when the user explicitly requests it.

Do not describe a model as successful when it only improves an intermediate metric. Explicitly state when governance correctly prevents deployment.

## Completion Checklist

- [ ] Changed path and acceptance criteria are identified.
- [ ] One falsifiable hypothesis and focused check were used.
- [ ] No-lookahead and configuration-flexibility checks exist where relevant.
- [ ] Artifact integrity and tamper detection were verified where relevant.
- [ ] API/RBAC/input validation was verified where relevant.
- [ ] Focused tests passed, or failures are reported with cause.
- [ ] Full tests were run when dependencies and time allowed.
- [ ] OOS evidence includes costs, benchmark, EV, drawdown, and reproducibility details.
- [ ] No live-trading action or safety bypass occurred.
- [ ] Final disposition is `APPROVED`, `CANDIDATE`, or `REJECTED` with evidence.
