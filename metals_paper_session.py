"""Metals paper daily session — PaperBroker pipeline for precious metals.

This session runs ``MetalsTrendFollowStrategy`` against the ``MetalsProvider``
(yfinance) data through the standard ``build_default_pipeline`` (PaperBroker).
The trading calendar follows COMEX Globex hours (America/New_York); for daily
bars the distinction is minor but we document it here for future intraday use.

Modes:
    --smoke       load cached data + verify pipeline wiring (no orders)
    --dry-run     full path with dry_run engine (no real broker orders)
    --now         immediate full session against the latest daily candle
    (default)     wait for a valid trading timestamp (always proceeds for daily
                  bars; COMEX is nearly 24/7, closed only Saturday).

Environment:
    PYROBOT_DATA_DIR    root for data/ (default ".")
    PYROBOT_UNIVERSE    comma-separated metals symbols (default GC=F,SI=F,GLD,SLV)

Run:
    .venv/bin/python metals_paper_session.py --smoke
    .venv/bin/python metals_paper_session.py --now
    .venv/bin/python metals_paper_session.py --dry-run
"""
from __future__ import annotations

import json
import os
import sys
import time as _sleep
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from pyrobot.data.metals_provider import DEFAULT_METALS, MetalsProvider, TRADING_CALENDAR

_EASTERN = ZoneInfo("America/New_York")

MODE_AUTO = "auto"
MODE_SMOKE = "smoke"
MODE_DRY_RUN = "dry-run"
MODE_NOW = "now"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _et_now() -> datetime:
    return datetime.now(_EASTERN)


def _session_date() -> str:
    return _utc_now().strftime("%Y-%m-%d")


def _parse_args(argv: List[str]) -> Dict[str, Any]:
    symbols = [s.strip().upper() for s in os.environ.get("PYROBOT_UNIVERSE", ",".join(DEFAULT_METALS)).split(",") if s.strip()]
    mode: str = MODE_AUTO
    seed_bars = 300
    data_dir = os.environ.get("PYROBOT_DATA_DIR", ".")

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--smoke":
            mode = MODE_SMOKE
        elif arg == "--dry-run":
            mode = MODE_DRY_RUN
        elif arg == "--now":
            mode = MODE_NOW
        elif arg == "--symbols" and i + 1 < len(argv):
            symbols = [s.strip().upper() for s in argv[i + 1].split(",") if s.strip()]
            i += 2; continue
        elif arg == "--seed-bars" and i + 1 < len(argv):
            seed_bars = max(1, int(argv[i + 1]))
            i += 2; continue
        elif arg == "--data-dir" and i + 1 < len(argv):
            data_dir = argv[i + 1]
            i += 2; continue
        i += 1
    return {"mode": mode, "symbols": symbols, "seed_bars": seed_bars, "data_dir": Path(data_dir).resolve()}


def _report_dir(root: Path) -> Path:
    p = root / "data" / "reports"; p.mkdir(parents=True, exist_ok=True); return p

def _audit_dir(root: Path) -> Path:
    p = root / "data" / "audit"; p.mkdir(parents=True, exist_ok=True); return p

def _save_report(payload: Dict[str, Any], root: Path) -> Path:
    out = _report_dir(root) / f"metals_paper_session_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out

def _session_log_path(root: Path) -> Path:
    return _report_dir(root) / f"metals_paper_session_{_session_date()}.jsonl"

def _log_session(root: Path, event: str, **payload: Any) -> None:
    path = _session_log_path(root)
    line = {"ts": _utc_now().isoformat(), "event": event}
    line.update(payload)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, default=str) + "\n")


# ── Data seeding helpers ────────────────────────────────────────────────────────

def _seed_from_cache(provider: MetalsProvider, root: Path, symbol: str, seed_bars: int) -> Dict[str, Any]:
    """Load seed bars from the yfinance CSV cache (no network)."""
    cache_path = root / "data" / "metals" / f"{symbol.replace('=', '_')}.csv"
    if not cache_path.exists():
        return {"bars": [], "source": "cache_missing", "cached": False}
    df = pd.read_csv(cache_path, parse_dates=["datetime"], index_col="datetime")
    df = df.tz_localize("UTC") if df.index.tz is None else df
    df = df.sort_index().tail(seed_bars)
    bars = df.reset_index().to_dict("records")
    return {"bars": bars, "source": "cache", "cached": True}


def _fetch_current_daily_bar(provider: MetalsProvider, symbol: str, root: Path) -> Optional[Dict[str, Any]]:
    """Fetch today's (or most recent) daily bar — yfinance cache only."""
    cache_path = root / "data" / "metals" / f"{symbol.replace('=', '_')}.csv"
    if not cache_path.exists():
        # Download minimal 30-day history via provider
        provider._cache.pop(symbol, None)
        provider._load_or_download(symbol)
        if not cache_path.exists():
            return None
    df = pd.read_csv(cache_path, parse_dates=["datetime"], index_col="datetime")
    df = df.tz_localize("UTC") if df.index.tz is None else df
    if df.empty:
        return None
    last = df.iloc[-1]
    return {
        "open": float(last["open"]),
        "high": float(last["high"]),
        "low": float(last["low"]),
        "close": float(last["close"]),
        "volume": float(last["volume"]),
        "datetime": df.index[-1].to_pydatetime(),
    }


# ── Modes ──────────────────────────────────────────────────────────────────────

def run_smoke(opts: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    """Load cached data + verify pipeline wiring — no orders, no network required."""
    symbols = opts["symbols"]
    provider = MetalsProvider(symbols=symbols, data_dir=opts["data_dir"] / "data" / "metals")
    print("=" * 72)
    print("PyRobot — Metals Paper Session SMOKE (cached data + pipeline wiring)")
    print("=" * 72)
    print(f"Universe: {', '.join(symbols)}")
    print(f"Trading calendar: {TRADING_CALENDAR['name']} ({TRADING_CALENDAR['hours']})")

    seeded: Dict[str, Any] = {}
    seed_entries: Dict[str, List[Any]] = {}
    for sym in symbols:
        entry = _seed_from_cache(provider, opts["data_dir"], sym, opts["seed_bars"])
        seeded[sym] = {"source": entry["source"], "bars": len(entry["bars"])}
        seed_entries[sym] = entry["bars"]
        print(f"   {sym}: seeded {len(entry['bars'])} daily bars from {entry['source']}")

    # Verify pipeline wiring
    print("Building paper pipeline (auth + wiring check) ...")
    from pyrobot.runtime.loop import build_default_pipeline
    from pyrobot.strategies.metals_trend import MetalsTrendFollowStrategy

    strategy = MetalsTrendFollowStrategy(strategy_id="metals_trend", symbols=symbols)
    pipeline = build_default_pipeline(symbols=symbols, initial_balance=100_000.0, strategy=strategy)
    counts = pipeline.seed_history(seed_entries)
    print(f"Pipeline ready: history seeded {counts}")

    report.update({
        "status": "completed", "session_date": _session_date(),
        "seeded": seeded, "pipeline_ok": True,
        "trading_calendar": TRADING_CALENDAR,
    })
    return report


def run_session(opts: Dict[str, Any], report: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
    """Full session: seed → current bar → process → settle → report."""
    symbols = opts["symbols"]
    root = opts["data_dir"]
    audit_path = str(_audit_dir(root) / f"metals_paper_session_{_session_date()}.jsonl")
    provider = MetalsProvider(symbols=symbols, data_dir=root / "data" / "metals")

    from pyrobot.runtime.loop import build_default_pipeline
    from pyrobot.strategies.metals_trend import MetalsTrendFollowStrategy

    strategy = MetalsTrendFollowStrategy(strategy_id="metals_trend", symbols=symbols)
    print("1. Building paper pipeline ...")
    pipeline = build_default_pipeline(
        symbols=symbols, initial_balance=100_000.0, audit_path=audit_path, strategy=strategy,
    )
    report["dry_run"] = dry_run
    report["audit_path"] = audit_path
    report["trading_calendar"] = TRADING_CALENDAR

    print("2. Seeding daily history ...")
    seed_entries: Dict[str, List[Any]] = {}
    seeded: Dict[str, Any] = {}
    for sym in symbols:
        _log_session(root, "seeding", symbol=sym)
        entry = _seed_from_cache(provider, root, sym, opts["seed_bars"])
        seeded[sym] = {"source": entry["source"], "bars": len(entry["bars"])}
        seed_entries[sym] = entry["bars"]
        print(f"   {sym}: {len(entry['bars'])} bars ({entry['source']})")
        _log_session(root, "seeded", symbol=sym, bars=len(entry["bars"]), source=entry["source"])
    pipeline.seed_history(seed_entries)
    report["seeded"] = seeded

    print("3. Fetching latest daily candle ...")
    bars: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    for sym in symbols:
        b = _fetch_current_daily_bar(provider, sym, root)
        if b is not None:
            bars[sym] = b
        else:
            missing.append(sym)
    if missing:
        report["missing_symbols"] = missing
        print(f"   No cached data for: {', '.join(missing)}")

    if not bars:
        report["status"] = "no_data"
        report["reason"] = "No cached daily bar available for any symbol."
        print(f"   [skip] {report['reason']}")
        return report

    bar_ts = max(b["datetime"] for b in bars.values())
    report["current_daily_candle"] = {
        s: {"close": round(float(b["close"]), 2), "date": b["datetime"].isoformat()}
        for s, b in bars.items()
    }
    print(f"   Current daily bar date: {bar_ts.isoformat()}")

    print("4. Processing one daily bar through the pipeline ...")
    result = pipeline.process_bar(bars, timestamp=bar_ts)
    report["process_result"] = {
        "timestamp": result["timestamp"], "bar_index": result["bar_index"],
        "equity": round(float(result["equity"]), 2),
        "kill_switch_active": result["kill_switch_active"],
    }
    for sig in result["signals"]:
        _log_session(root, "signal", symbol=sig.get("symbol"), action=sig.get("action"), reason=sig.get("reason"))
        print(f"   [signal] {sig.get('symbol')}: {sig.get('action')} — {sig.get('reason')}")

    print("5. Settling orders ...")
    settled = []
    for _ in range(5):
        active = pipeline.order_manager.active_orders()
        if not active:
            break
        for order in list(active):
            settled.append({
                "client_order_id": order.client_order_id, "symbol": order.symbol,
                "side": order.side.value, "status": order.status.value,
                "filled_quantity": order.filled_quantity, "avg_fill_price": order.avg_fill_price,
            })
        _sleep.sleep(0.1)
    for s in settled:
        _log_session(root, "order_status", **{k: v for k, v in s.items()})
        print(f"   [order] {s.get('symbol')} {s.get('side')} → {s.get('status')} filled={s.get('filled_quantity')}")
    report["orders_settled"] = settled

    orders = pipeline.order_manager.all_orders()
    report["orders_count"] = len(orders)
    report["status"] = "completed"
    report["equity"] = report["process_result"]["equity"]
    report["positions"] = result["positions"]
    _log_session(root, "session_end", status="completed", equity=report["equity"],
                 orders=sorted(f"{o.side.value}:{o.status.value}" for o in orders))
    return report


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    report: Dict[str, Any] = {
        "title": "Metals Paper Session — MetalsTrendFollowStrategy (PaperBroker)",
        "generated_at": _utc_now().isoformat(),
        "session_date": _session_date(),
        "status": "running",
    }
    try:
        opts = _parse_args(sys.argv[1:])
    except ValueError as exc:
        print(f"[error] {exc}"); sys.exit(1)
    report["symbols"] = opts["symbols"]
    report["mode"] = opts["mode"]
    _log_session(opts["data_dir"], "session_start", mode=opts["mode"], symbols=opts["symbols"])

    mode = opts["mode"]
    if mode == MODE_SMOKE:
        run_smoke(opts, report)
    else:
        try:
            run_session(opts, report, dry_run=(mode == MODE_DRY_RUN))
        except Exception as exc:
            import traceback
            report["status"] = "error"
            report["error"] = str(exc)
            traceback.print_exc()
            _log_session(opts["data_dir"], "session_end", status="error", error=str(exc))
            print(f"Report: {_save_report(report, opts['data_dir'])}")
            sys.exit(1)

    _log_session(opts["data_dir"], "session_end", status=report["status"])
    out = _save_report(report, opts["data_dir"])
    print(f"\nSession report: {out}")
    print(f"Session log:    {_session_log_path(opts['data_dir'])}")
    print("Done.")


if __name__ == "__main__":
    main()
