"""Operational metrics and daily reporting for production paper trading."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyrobot.audit.ledger import AuditAction, AuditLedger


@dataclass
class RuntimeMetrics:
    """Append-only runtime metrics snapshot writer."""

    output_path: Optional[str | Path] = None
    snapshots: List[Dict[str, Any]] = field(default_factory=list)

    def record_snapshot(self, summary: dict, pipeline_status: dict) -> dict:
        equity = float(summary.get("equity", 0.0) or 0.0)
        previous_peak = max([float(s.get("equity", 0.0)) for s in self.snapshots], default=equity)
        peak = max(previous_peak, equity)
        drawdown = 0.0 if peak <= 0 else (peak - equity) / peak
        orders = summary.get("orders", [])
        snapshot = {
            "timestamp": summary.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "equity": equity,
            "drawdown": drawdown,
            "positions": summary.get("positions", {}),
            "orders_count": len(orders),
            "rejected_orders": sum(1 for o in orders if str(o.get("status", "")).upper() in {"REJECTED", "ERROR"}),
            "kill_switch_active": bool(summary.get("kill_switch_active")),
            "model_risk_scale": pipeline_status.get("model_risk_scale"),
            "open_orders": pipeline_status.get("open_orders"),
        }
        self.snapshots.append(snapshot)
        if self.output_path is not None:
            path = Path(self.output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot, default=str) + "\n")
        return snapshot


def build_daily_report(
    ledger: AuditLedger,
    *,
    report_date: Optional[date] = None,
    output_path: Optional[str | Path] = None,
) -> dict:
    """Summarize a day's audited trading activity."""
    target = report_date or datetime.now(timezone.utc).date()
    events = [
        e for e in ledger.get_events()
        if e.timestamp.astimezone(timezone.utc).date() == target
    ]
    actions: Dict[str, int] = {}
    for event in events:
        actions[event.action.value] = actions.get(event.action.value, 0) + 1
    report = {
        "date": target.isoformat(),
        "total_events": len(events),
        "actions": actions,
        "orders_submitted": actions.get(AuditAction.ORDER_SUBMITTED.value, 0),
        "orders_filled": actions.get(AuditAction.ORDER_FILLED.value, 0),
        "orders_rejected": actions.get(AuditAction.ORDER_REJECTED.value, 0),
        "drift_checks": actions.get(AuditAction.MODEL_DRIFT_CHECK.value, 0),
        "kill_switch_events": actions.get(AuditAction.KILL_SWITCH_TRIGGERED.value, 0),
        "ledger_integrity": ledger.verify_file_integrity(),
    }
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report
