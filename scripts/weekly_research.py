"""Weekly research session — multi-market benchmark check + research-log entry.

Scheduled by cron every Saturday (10:00 Africa/Cairo). Runs the multi-market
benchmark aggregator (``scripts/multi_market_comparison.py``), then appends a
dated findings stub to the continuous research log that records how each
strategy performed against its Buy & Hold benchmark.

The "scan reference library → findings → decision" content is filled by the
follow-up review, per the Research Before Building standard
(`docs/professional_development_standard.md`).

Run:  .venv/bin/python scripts/weekly_research.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "reports" / "continuous_research_log.md"
PITFALL_FILE = ROOT / "docs" / "professional_development_standard.md"
COMPARISON_FILE = ROOT / "data" / "reports" / "multi_market_comparison.json"


def _load_comparison() -> List[Dict[str, Any]]:
    """Load the multi-market comparison report, or regenerate it if missing."""
    if not COMPARISON_FILE.exists():
        sys.path.insert(0, str(ROOT / "scripts"))
        import multi_market_comparison

        multi_market_comparison.main()
    if not COMPARISON_FILE.exists():
        return []
    data = json.loads(COMPARISON_FILE.read_text(encoding="utf-8"))
    return data.get("strategies", [])


def _benchmark_markdown(strategies: List[Dict[str, Any]]) -> str:
    """Render a compact benchmark table for the research log."""
    lines = ["| Strategy | Market | Strategy % | Buy & Hold % | Outcome |"]
    lines.append("|---|---|---:|---:|---|")
    for s in strategies:
        st = s.get("strategy_return_pct")
        bh = s.get("buy_and_hold_return_pct")
        st_s = f"{st}%" if st is not None else "n/a"
        bh_s = f"{bh}%" if bh is not None else "n/a"
        outcome = "BEAT benchmark" if s.get("beat_benchmark") else "behind benchmark"
        lines.append(f"| {s.get('strategy', '')} | {s.get('market', '')} | {st_s} | {bh_s} | {outcome} |")
    return "\n".join(lines)


def main() -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    strategies = _load_comparison()
    benchmark_lines = ""
    if strategies:
        benchmark_lines = (
            "**Multi-market benchmarks (Buy & Hold comparison):**\n\n"
            + _benchmark_markdown(strategies)
        )

    entry = f"""
---

## {today} — Weekly research session (scheduled)

**Question:** How do each market's strategies compare against their Buy & Hold benchmark this week?

**Sources:** Pending follow-up library scan.

**Findings:**
- {today}: scheduled weekly research session ran.
{benchmark_lines}
- Scan the reference library for updates / reported errors, then replace this
  stub with the findings, comparison, and decision (see the Entry Template above
  and the seven-pitfall checklist in `{PITFALL_FILE.name}`).

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


if __name__ == "__main__":
    main()
