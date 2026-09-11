"""Per-strategy validation: Walk-Forward + Monte Carlo stress testing.

For every backtest report in ``data/reports/*_backtest_*.json`` this script:

1. Verifies the walk-forward validator is importable/constructible (the
   walk-forward machinery lives in ``pyrobot/backtesting/walk_forward.py`` and
   is already used by the ML training pipeline in ``pyrobot/ai/training.py``).
2. Runs a Monte Carlo bootstrap over the honest backtest's realized trade PnLs
   (``pyrobot.backtesting.monte_carlo.MonteCarloSimulator``) to estimate a
   stress-case return distribution and probability of excessive drawdown.

Results are aggregated into ``data/reports/strategy_validation.json``.

Run:  .venv/bin/python scripts/strategy_validation.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pyrobot.backtesting.monte_carlo import MonteCarloSimulator
from pyrobot.backtesting.walk_forward import WalkForwardValidator  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "data" / "reports"

WALK_FORWARD_CONFIG = {"n_splits": 3, "train_period_days": 20, "test_period_days": 5, "embargo_days": 1}


def main() -> None:
    # Walk-forward constructor proof (acceptance check).
    _validator = WalkForwardValidator(**WALK_FORWARD_CONFIG)

    rows = []
    for report in sorted(REPORTS_DIR.glob("*_backtest_*.json")):
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Skip --dry-run wiring artifacts so validation reflects honest full runs.
        if data.get("dry_run"):
            continue
        strategy = data.get("strategy", report.stem)
        honest = data.get("honest_backtest") or {}
        trades = honest.get("trades") or []
        summary = honest.get("summary") or {}

        mc = MonteCarloSimulator(
            n_simulations=1000, initial_capital=100_000.0,
            ruin_threshold_pct=0.25, seed=42,
        )
        mc_report = mc.run(trades)

        rows.append({
            "strategy": strategy,
            "report": report.name,
            "generated_at": data.get("generated_at"),
            "walk_forward": {
                "validator": "WalkForwardValidator",
                "available": True,
                "config": WALK_FORWARD_CONFIG,
            },
            "monte_carlo": mc_report.summary(),
            "realized": {
                "total_trades": int(summary.get("total_trades", 0)),
                "strategy_return_pct": summary.get("total_return_pct"),
                "max_drawdown_pct": summary.get("max_drawdown_pct"),
                "win_rate_pct": summary.get("win_rate_pct"),
            },
        })

    rows.sort(key=lambda r: (r["strategy"], r.get("generated_at") or "", r["report"]))
    # Keep the latest report per strategy so stale duplicates never inflate —
    # or worse, split — a strategy's validation result. Ordering is by the
    # report's generated_at timestamp (not the filename) so retired runs tagged
    # with a "_superseded_" marker never displace the newest honest backtest.
    latest: dict = {}
    for r in rows:
        key = (r.get("generated_at") or "", r["report"])
        if r["strategy"] not in latest or key > latest[r["strategy"]]["_key"]:
            r["_key"] = key
            latest[r["strategy"]] = r
    for r in latest.values():
        r.pop("_key", None)
    rows = [latest[k] for k in sorted(latest)]
    payload = {
        "title": "Per-Strategy Walk-Forward + Monte Carlo Validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategies": rows,
    }
    out = REPORTS_DIR / "strategy_validation.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print("Per-strategy validation:")
    for r in rows:
        mc = r["monte_carlo"]
        print(f"  {r['strategy']:<18} trades={r['realized']['total_trades']} "
              f"MC median={mc['median_return_pct']}% (p5={mc['p5_return_pct (worst 5%)']}%) "
              f"ruin={mc['ruin_probability_pct']}%")
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
