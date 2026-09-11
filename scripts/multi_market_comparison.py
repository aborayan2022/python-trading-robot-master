"""Aggregate per-market backtest results into a multi-market comparison report.

Reads every ``{strategy}_backtest_*.json`` from ``data/reports/`` and writes a
combined comparison to ``data/reports/multi_market_comparison.json`` with, for
each strategy/market:

    - honest strategy return vs Buy & Hold (benchmark) return
    - Sharpe, max drawdown, trade count, win rate
    - whether the strategy beat Buy & Hold in that market

Provenance gate (governance §3b, `docs/professional_development_standard.md`):
a report whose latest run lacks a ``provenance.git_commit`` or was generated
from a dirty tree is not a release candidate. Such strategies are still listed
(so the problem is visible) but the script exits non-zero, failing the weekly
research session until the reports are regenerated from a clean commit.

Run:  .venv/bin/python scripts/multi_market_comparison.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "data" / "reports"

MARKET_LABELS = {
    "USTrendFollowStrategy": "US equities (trend-follow)",
    "us_trend": "US equities (trend-follow)",
    "us_mean_reversion": "US equities (mean reversion)",
    "us_breakout": "US equities (breakout)",
    "metals_trend": "Precious metals (trend-follow)",
    "metals_momentum": "Precious metals (momentum)",
    "crypto_trend": "Crypto (trend / breakout)",
    "crypto_mean_rev": "Crypto (mean reversion)",
}

# Group strategies into real markets (3) instead of one "market" per strategy (7),
# so market_count reflects actual markets traded.
MARKET_GROUPS = {
    "USTrendFollowStrategy": "US",
    "us_trend": "US",
    "us_mean_reversion": "US",
    "us_breakout": "US",
    "metals_trend": "Metals",
    "metals_momentum": "Metals",
    "crypto_trend": "Crypto",
    "crypto_mean_rev": "Crypto",
}


def _provenance_ok(data: dict) -> bool:
    """A report is aggregation-eligible only with a commit SHA from a clean tree."""
    prov = data.get("provenance") or {}
    return bool(prov.get("git_commit")) and prov.get("dirty_tree") is False


def main() -> None:
    rows = []
    for report in sorted(REPORTS_DIR.glob("*_backtest_*.json")):
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Skip --dry-run wiring artifacts so the comparison shows honest full runs.
        if data.get("dry_run"):
            continue
        strategy = data.get("strategy", report.stem)
        honest = (data.get("honest_backtest") or {}).get("summary", {})
        bh = (data.get("buy_and_hold") or {}).get("summary", {})
        total_return = honest.get("total_return_pct")
        bh_return = bh.get("total_return_pct")
        prov = data.get("provenance") or {}
        rows.append({
            "strategy": strategy,
            "market": MARKET_GROUPS.get(strategy, strategy),
            "strategy_label": MARKET_LABELS.get(strategy, strategy),
            "report": report.name,
            "generated_at": data.get("generated_at"),
            "symbols": data.get("symbols", []),
            "strategy_return_pct": total_return,
            "buy_and_hold_return_pct": bh_return,
            "beat_benchmark": (total_return is not None and bh_return is not None
                               and total_return > bh_return),
            "sharpe_ratio": honest.get("sharpe_ratio"),
            "max_drawdown_pct": honest.get("max_drawdown_pct"),
            "total_trades": honest.get("total_trades"),
            "win_rate_pct": honest.get("win_rate_pct"),
            "provenance": {
                "git_commit": prov.get("git_commit"),
                "dirty_tree": prov.get("dirty_tree"),
                "ok": _provenance_ok(data),
            },
        })

    rows.sort(key=lambda r: (r["strategy"], r.get("generated_at") or ""))
    # Keep the latest report per strategy when multiple runs exist.
    latest: dict = {}
    for r in rows:
        if r["strategy"] not in latest or (r.get("generated_at") or "") > (latest[r["strategy"]].get("generated_at") or ""):
            latest[r["strategy"]] = r

    rejected = [r for r in latest.values() if not r["provenance"]["ok"]]
    for r in rejected:
        print(f"PROVENANCE REJECTED: {r['strategy']} -> {r['report']} "
              f"(git_commit={r['provenance']['git_commit']!r}, "
              f"dirty_tree={r['provenance']['dirty_tree']!r}). Regenerate from a clean "
              "commit before this comparison is eligible as a release aggregate.",
              file=sys.stderr)

    comparison = {
        "title": "Multi-Market Backtest Comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market_count": len({r["market"] for r in latest.values()}),
        "strategy_count": len(latest),
        "strategies": [latest[k] for k in sorted(latest)],
    }
    out = REPORTS_DIR / "multi_market_comparison.json"
    out.write_text(json.dumps(comparison, indent=2, default=str), encoding="utf-8")

    print(f"Multi-market comparison: {len(latest)} strategies across "
          f"{comparison['market_count']} markets")
    for row in comparison["strategies"]:
        beat = "BEAT" if row["beat_benchmark"] else "behind"
        print(f"  {row['strategy']:<18} strategy={row['strategy_return_pct']}%  "
              f"buy&hold={row['buy_and_hold_return_pct']}%  ({beat})")
    print(f"Report: {out}")

    if rejected:
        sys.exit(1)


if __name__ == "__main__":
    main()
