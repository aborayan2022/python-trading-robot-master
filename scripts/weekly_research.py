"""Weekly research session — aggregate refresh + provenance-gated benchmark check.

Scheduled by cron every Saturday (10:00 Africa/Cairo). Regenerates the
multi-market comparison and validation aggregates (so comparison tables are
always current), verifies that every strategy's selected report carries valid
provenance (governance §3b — missing ``git_commit`` or dirty-tree runs are
rejected), and appends a dated findings stub to the continuous research log.

Per the Wave-5 close-out order (consultant approval §6), a weekly report with
any PROVENANCE REJECTED strategy is invalid: the run exits non-zero and the
stub is still written with the rejection list so the operator sees what must be
regenerated.

Run:  .venv/bin/python scripts/weekly_research.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "reports" / "continuous_research_log.md"
PITFALL_FILE = ROOT / "docs" / "professional_development_standard.md"
REPORTS_DIR = ROOT / "data" / "reports"
COMPARISON_FILE = REPORTS_DIR / "multi_market_comparison.json"


def _run_aggregator(name: str) -> int:
    """Regenerate one aggregate in a subprocess; return its exit code."""
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name)],
        capture_output=True, text=True,
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def _load_comparison() -> List[Dict[str, Any]]:
    """Regenerate both aggregates, then load the comparison strategies list."""
    if not COMPARISON_FILE.exists():
        _run_aggregator("multi_market_comparison.py")
    data = json.loads(COMPARISON_FILE.read_text(encoding="utf-8"))
    return data.get("strategies", [])


def _benchmark_markdown(strategies: List[Dict[str, Any]]) -> str:
    """Render a compact benchmark table for the research log."""
    lines = ["| Strategy | Market | Strategy % | Buy & Hold % | Outcome | Provenance |"]
    lines.append("|---|---|---:|---:|---|---|")
    for s in strategies:
        st = s.get("strategy_return_pct")
        bh = s.get("buy_and_hold_return_pct")
        st_s = f"{st}%" if st is not None else "n/a"
        bh_s = f"{bh}%" if bh is not None else "n/a"
        outcome = "BEAT benchmark" if s.get("beat_benchmark") else "behind benchmark"
        prov = s.get("provenance", {})
        prov_s = "OK" if prov.get("ok") else "REJECTED"
        lines.append(f"| {s.get('strategy', '')} | {s.get('market', '')} | {st_s} | {bh_s} | {outcome} | {prov_s} |")
    return "\n".join(lines)


def _rejected(strategies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [s for s in strategies if not (s.get("provenance") or {}).get("ok")]


def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    comparison_rc = _run_aggregator("multi_market_comparison.py")
    validation_rc = _run_aggregator("strategy_validation.py")
    strategies = _load_comparison()

    rejected = _rejected(strategies)
    benchmark_lines = ""
    if strategies:
        benchmark_lines = (
            "**Multi-market benchmarks (Buy & Hold comparison):**\n\n"
            + _benchmark_markdown(strategies)
        )

    provenance_lines = ""
    if rejected:
        provenance_lines = (
            "\n**Provenance gate — REJECTED (invalid weekly aggregate):**\n"
            + "\n".join(
                f"- `{s.get('strategy', '')}` → `{s.get('report', '')}` "
                f"(git_commit={s.get('provenance', {}).get('git_commit')!r}, "
                f"dirty_tree={s.get('provenance', {}).get('dirty_tree')!r})"
                for s in rejected
            )
        )

    repair = ""
    if rejected or comparison_rc != 0 or validation_rc != 0:
        repair = (
            "\n\n**Required before this week's report is accepted:** regenerate the "
            "rejected reports from a clean commit (`dirty_tree=false`) and re-run "
            "`scripts/weekly_research.py`."
        )

    entry = f"""
---

## {today} — Weekly research session (scheduled)

**Question:** How do each market's strategies compare against their Buy & Hold benchmark this week?

**Sources:** Pending follow-up library scan.

**Findings:**
- {today}: scheduled weekly research session ran; aggregates regenerated
  (multi_market_comparison.py, strategy_validation.py) and provenance-verified.
{benchmark_lines}
{provenance_lines}
- Scan the reference library for updates / reported errors, then replace this
  stub with the findings, comparison, and decision (see the Entry Template above
  and the seven-pitfall checklist in `{PITFALL_FILE.name}`).
{repair}
**Comparison with our use case:** Pending.

**Decision / Lesson:** Pending.

**Impact on code:**
- none — decision pending.

"""
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(entry)
    print(f"appended {today} research-session stub to {LOG_PATH}")
    if strategies:
        print(f"multi-market benchmarks recorded: {len(strategies)} strategies")

    if rejected:
        print(f"PROVENANCE REJECTED: {len(rejected)} strategy/ies — weekly aggregate invalid.", file=sys.stderr)
    if comparison_rc != 0:
        print("multi_market_comparison.py exited non-zero.", file=sys.stderr)
    if validation_rc != 0:
        print("strategy_validation.py exited non-zero.", file=sys.stderr)
    if rejected or comparison_rc != 0 or validation_rc != 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
