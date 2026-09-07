"""US paper daily session — real Alpaca paper pipeline, one daily bar per day.

This is the production daily execution path for ``USTrendFollowStrategy``. It
runs the *exact* production pipeline (``build_alpaca_pipeline``) once per
trading day via a single ``process_bar`` call:

    env/keys → build Alpaca paper pipeline + strategy + sector map
            → seed ~300 daily candles (Alpaca history, CSV cache fallback)
            → sync broker positions (strategy + risk book)
            → fetch today's daily candle → one process_bar → settle orders
            → JSON report (data/reports/) + JSONL session log

Modes:
    --smoke     connectivity + historical-seeding check only (no evaluation,
                no orders). Works while the market is closed.
    --dry-run   shadow mode — full path but no broker orders (dry_run engine).
    --now       immediate full session against the latest daily candle.
    (default)   wait for the pre-close window (15:30–16:00 ET) on a trading
                day; gracefully skips (status "market_closed") otherwise.

Environment:
    PYROBOT_DATA_DIR   root for data/ (default ".")
    PYROBOT_SYMBOLS    comma-separated universe (default the ten cache symbols)
    ALPACA_API_KEY / ALPACA_SECRET_KEY  (loaded from .env via python-dotenv)

Exit codes:
    0  success or graceful skip (market closed / missing credentials)
    1  session error (pipeline failure)
    2  missing alpaca-py dependency

Run:
    .venv/bin/python us_paper_session.py --smoke
    .venv/bin/python us_paper_session.py --now
    .venv/bin/python us_paper_session.py --dry-run
"""

from __future__ import annotations

import json
import os
import sys
import time as _sleep
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from pyrobot.data.alpaca import AlpacaDataProvider
from pyrobot.data.base import DataFrequency
from pyrobot.data.sectors import build_sector_map

_EASTERN = ZoneInfo("America/New_York")

DEFAULT_UNIVERSE = ["AAPL", "AMZN", "GOOGL", "JNJ", "JPM", "META", "MSFT", "NVDA", "WMT", "XOM"]
MONITORING_YEAR = 2026
PRE_CLOSE_START = time(15, 30)
PRE_CLOSE_END = time(16, 0)

MODE_AUTO = "auto"
MODE_SMOKE = "smoke"
MODE_DRY_RUN = "dry-run"
MODE_NOW = "now"


def _et_now() -> datetime:
    return datetime.now(_EASTERN)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _session_date() -> str:
    """Trading-day label (America/New_York date)."""
    return _et_now().strftime("%Y-%m-%d")


# ── CLI ──────────────────────────────────────────────────────────────────────

def _parse_args(argv: List[str]) -> Dict[str, Any]:
    symbols = [s.strip().upper() for s in os.environ.get("PYROBOT_SYMBOLS", ",".join(DEFAULT_UNIVERSE)).split(",") if s.strip()]
    mode: str = MODE_AUTO
    seed_bars = 300
    lookback_days = 700
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
            i += 2
            continue
        elif arg == "--seed-bars" and i + 1 < len(argv):
            seed_bars = max(1, int(argv[i + 1]))
            i += 2
            continue
        elif arg == "--lookback-days" and i + 1 < len(argv):
            lookback_days = max(1, int(argv[i + 1]))
            i += 2
            continue
        elif arg == "--data-dir" and i + 1 < len(argv):
            data_dir = argv[i + 1]
            i += 2
            continue
        i += 1

    if mode not in (MODE_AUTO, MODE_SMOKE, MODE_DRY_RUN, MODE_NOW):
        raise ValueError(f"Unknown mode: {mode}")
    return {
        "mode": mode,
        "symbols": symbols or DEFAULT_UNIVERSE,
        "seed_bars": seed_bars,
        "lookback_days": lookback_days,
        "data_dir": Path(data_dir).resolve(),
    }


# ── Reporting / logging ──────────────────────────────────────────────────────

def _report_dir(root: Path) -> Path:
    path = root / "data" / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _audit_dir(root: Path) -> Path:
    path = root / "data" / "audit"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_report(payload: Dict[str, Any], root: Path) -> Path:
    out = _report_dir(root) / f"us_paper_session_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out


def _session_log_path(root: Path) -> Path:
    return _report_dir(root) / f"us_paper_session_{_session_date()}.jsonl"


def _log_session(root: Path, event: str, **payload: Any) -> None:
    """Append one event line to the JSONL session log."""
    path = _session_log_path(root)
    line = {"ts": _utc_now().isoformat(), "event": event}
    line.update(payload)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, default=str) + "\n")


# ── Session gates ────────────────────────────────────────────────────────────

def _preclose_wait_seconds(now_et: datetime) -> Optional[float]:
    """Seconds until the pre-close window, or None when the session is skipped.

    Weekends (and anything outside a regular weekday window we can still
    trade) skip. Before 15:30 ET on a weekday we wait; inside the window we
    return 0; after 16:00 ET the daily candle is complete and we run now.
    """
    if now_et.weekday() >= 5:
        return None
    now_time = now_et.time()
    if now_time < PRE_CLOSE_START:
        target = datetime.combine(now_et.date(), PRE_CLOSE_START, tzinfo=_EASTERN)
        return max(0.0, (target - now_et).total_seconds())
    if now_time <= PRE_CLOSE_END:
        return 0.0
    return 0.0  # after close — today's daily bar is complete, proceed


# ── Data helpers ─────────────────────────────────────────────────────────────

def _cache_csv_path(root: Path, symbol: str) -> Path:
    return root / "data" / "us_market" / f"{symbol.upper()}.csv"


def _load_cache_rows(root: Path, symbol: str, seed_bars: int) -> List[Dict[str, Any]]:
    import pandas as pd

    path = _cache_csv_path(root, symbol)
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if "datetime" not in df.columns:
        return []
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.sort_values("datetime").tail(seed_bars)
    records = df.to_dict("records")
    return records if isinstance(records, list) else []


def _seed_candles_for_symbol(
    data_provider: AlpacaDataProvider,
    root: Path,
    symbol: str,
    seed_bars: int,
    lookback_days: int,
) -> Dict[str, Any]:
    """Fetch daily history, falling back to the CSV cache on API failure.

    Returns: {"bars": [Candle.to_dict(), ...], "source": ..., "cached": bool}
    """
    now = _utc_now()
    try:
        candles = data_provider.get_historical_candles(
            symbol=symbol,
            start=now - timedelta(days=lookback_days),
            end=now,
            frequency=DataFrequency.DAILY,
        )
        seed = candles[-seed_bars:]
        if seed:
            return {
                "bars": [c.to_dict() for c in seed],
                "source": "alpaca",
                "cached": False,
            }
    except Exception as exc:
        # Fall through to the local CSV cache with the failure recorded.
        _log_session(root, "seed_api_error", symbol=symbol, error=str(exc))

    rows = _load_cache_rows(root, symbol, seed_bars)
    return {"bars": rows, "source": "cache", "cached": True}


def _fetch_current_daily_bars(
    data_provider: AlpacaDataProvider,
    symbols: List[str],
    *,
    fallback_to_latest: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Today's (partial) daily candle per symbol, or {} when none exists today.

    With ``fallback_to_latest`` (--now / --dry-run) symbols without a bar
    stamped today fall back to their most recent completed daily candle so
    the full path can be exercised even when the market is closed.
    """
    now = _utc_now()
    et_day = datetime.combine(_et_now().date(), time(0, 0), tzinfo=_EASTERN)
    day_start_utc = et_day.astimezone(timezone.utc)

    bars: Dict[str, Dict[str, Any]] = {}
    missing: List[str] = []
    for symbol in symbols:
        try:
            candles = data_provider.get_historical_candles(
                symbol=symbol,
                start=day_start_utc,
                end=now,
                frequency=DataFrequency.DAILY,
            )
        except Exception:
            candles = []
        if candles:
            c = candles[-1]
            bars[symbol] = {
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "datetime": c.timestamp,
            }
        else:
            missing.append(symbol)

    if missing and fallback_to_latest:
        for symbol in missing:
            try:
                candles = data_provider.get_historical_candles(
                    symbol=symbol,
                    start=now - timedelta(days=30),
                    end=now,
                    frequency=DataFrequency.DAILY,
                )
            except Exception:
                candles = []
            if candles:
                c = candles[-1]
                bars[symbol] = {
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "datetime": c.timestamp,
                }
    return bars


# ── Settlement ───────────────────────────────────────────────────────────────

def _settle_active_orders(
    pipeline,
    *,
    poll: bool = True,
    attempts: int = 5,
    sleep_s: float = 2.0,
) -> List[Dict[str, Any]]:
    """Settle working orders (poll broker) or just snapshot their status.

    ``poll=False`` (dry-run) skips broker polling entirely — dry-run orders
    carry synthetic ids the broker cannot resolve.
    """
    results: Dict[str, Dict[str, Any]] = {}
    for _ in range(attempts):
        active = pipeline.order_manager.active_orders()
        if not active:
            break
        for order in list(active):
            coid = order.client_order_id
            if not poll:
                results[coid] = {
                    "client_order_id": coid,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "status": order.status.value,
                    "broker_status": None,
                    "filled_quantity": order.filled_quantity,
                    "avg_fill_price": order.avg_fill_price,
                }
                continue
            try:
                broker_status = pipeline.execution_engine.poll_status(coid)
                results[coid] = {
                    "client_order_id": coid,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "status": order.status.value,
                    "broker_status": broker_status.get("status"),
                    "filled_quantity": order.filled_quantity,
                    "avg_fill_price": order.avg_fill_price,
                }
            except Exception as exc:
                results[coid] = {
                    "client_order_id": coid,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "status": order.status.value,
                    "error": str(exc),
                }
        if pipeline.order_manager.active_orders() and poll:
            _sleep.sleep(sleep_s)
    return list(results.values())


# ── Modes ────────────────────────────────────────────────────────────────────

def run_smoke(opts: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    """Connectivity + historical-seeding check (works with the market closed)."""
    symbols = opts["symbols"]
    data_provider = AlpacaDataProvider()
    print("=" * 72)
    print("PyRobot — US Paper Session SMOKE (connectivity + historical seeding)")
    print("=" * 72)
    print(f"Universe: {', '.join(symbols)}")

    seeded: Dict[str, Any] = {}
    seed_payload: Dict[str, List[Any]] = {}
    for symbol in symbols:
        entry = _seed_candles_for_symbol(
            data_provider, opts["data_dir"], symbol, opts["seed_bars"], opts["lookback_days"]
        )
        n = len(entry["bars"])
        seeded[symbol] = {"source": entry["source"], "bars": n, "cached": entry["cached"]}
        seed_payload[symbol] = entry["bars"]
        print(f"   {symbol}: seeded {n} daily bars from {entry['source']}")
        if entry["source"] == "cache" and not entry["cached"]:
            print(f"   {symbol}: no cache fallback available at "
                  f"{_cache_csv_path(opts['data_dir'], symbol)}")

    # Verify the full pipeline wiring (broker auth + strategy + sector map).
    print("Building Alpaca paper pipeline (auth + wiring check) ...")
    from pyrobot.runtime.loop import build_alpaca_pipeline
    from pyrobot.strategies.us_trend import USTrendFollowStrategy

    strategy = USTrendFollowStrategy(strategy_id="us_trend_follow", symbols=symbols)
    pipeline = build_alpaca_pipeline(
        symbols=symbols,
        profile="alpaca_paper",
        strategy=strategy,
        sector_map=build_sector_map(symbols),
    )
    counts = pipeline.seed_history(seed_payload)
    sector_covers = sum(1 for s in symbols if build_sector_map([s]).get(s) != "UNKNOWN")
    print(f"Pipeline ready: history seeded {counts}, sector map covers {sector_covers}/{len(symbols)} symbols")

    report.update({
        "status": "completed",
        "session_date": _session_date(),
        "seeded": seeded,
        "sector_map_coverage": f"{sector_covers}/{len(symbols)}",
        "pipeline_ok": True,
    })
    return report


def run_session(opts: Dict[str, Any], report: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
    """Full daily session: seed → sync → current bar → process → settle."""
    symbols = opts["symbols"]
    root = opts["data_dir"]
    audit_path = str(_audit_dir(root) / f"us_paper_session_{_session_date()}.jsonl")
    sector_map = build_sector_map(symbols)

    from pyrobot.runtime.loop import build_alpaca_pipeline
    from pyrobot.strategies.us_trend import USTrendFollowStrategy

    strategy = USTrendFollowStrategy(strategy_id="us_trend_follow", symbols=symbols)
    print("1. Building Alpaca paper pipeline ...")
    pipeline = build_alpaca_pipeline(
        symbols=symbols,
        profile="alpaca_paper",
        audit_path=audit_path,
        strategy=strategy,
        dry_run=dry_run,
        sector_map=sector_map,
    )
    report["dry_run"] = dry_run
    report["audit_path"] = audit_path
    report["sector_map"] = sector_map

    print("2. Seeding daily history (300 candles / symbol) ...")
    data_provider = AlpacaDataProvider()
    seeded: Dict[str, Any] = {}
    seed_entries: Dict[str, List[Any]] = {}
    for symbol in symbols:
        _log_session(root, "seeding", symbol=symbol)
        entry = _seed_candles_for_symbol(
            data_provider, root, symbol, opts["seed_bars"], opts["lookback_days"]
        )
        seeded[symbol] = {"source": entry["source"], "bars": len(entry["bars"])}
        seed_entries[symbol] = entry["bars"]
        print(f"   {symbol}: {len(entry['bars'])} bars ({entry['source']})")
        _log_session(root, "seeded", symbol=symbol, bars=len(entry["bars"]), source=entry["source"])
    pipeline.seed_history(seed_entries)
    report["seeded"] = seeded

    print("3. Syncing broker positions ...")
    positions_raw = pipeline.broker.get_positions() or []
    qty_map = {}
    avg_map = {}
    for p in positions_raw:
        sym = str(p.get("symbol", "")).upper()
        qty = float(p.get("quantity", 0.0) or 0.0)
        avg = float(p.get("average_price", 0.0) or 0.0)
        if sym:
            qty_map[sym] = qty
            avg_map[sym] = avg
    strategy.sync_positions(qty_map)
    for sym, avg in avg_map.items():
        pipeline.risk_manager.sync_position(sym, qty_map.get(sym, 0.0), avg)
    report["positions_synced"] = qty_map
    _log_session(root, "positions_synced", positions=qty_map)
    if qty_map:
        print(f"   Synchronized {len(qty_map)} position(s): {qty_map}")
    else:
        print("   No open positions to synchronize.")

    print("4. Fetching today's daily candle ...")
    mode = opts["mode"]
    bars = _fetch_current_daily_bars(
        data_provider, symbols, fallback_to_latest=(mode in (MODE_NOW, MODE_DRY_RUN))
    )
    if not bars:
        report["status"] = "market_closed"
        report["reason"] = "No daily bar stamped today (market closed / holiday)."
        print(f"   [skip] {report['reason']}")
        return report
    bar_ts = max(b["datetime"] for b in bars.values())
    report["current_daily_candle"] = {
        s: {"close": round(float(b["close"]), 2), "date": b["datetime"].isoformat()}
        for s, b in bars.items()
    }
    print(f"   Current daily bar date: {bar_ts.isoformat()}")

    print("5. Processing one daily bar through the full pipeline ...")
    result = pipeline.process_bar(bars, timestamp=bar_ts)
    report["process_result"] = {
        "timestamp": result["timestamp"],
        "bar_index": result["bar_index"],
        "equity": round(float(result["equity"]), 2),
        "kill_switch_active": result["kill_switch_active"],
    }
    for sig in result["signals"]:
        _log_session(root, "signal", symbol=sig.get("symbol"), action=sig.get("action"),
                     reason=sig.get("reason"))
        print(f"   [signal] {sig.get('symbol')}: {sig.get('action')} — {sig.get('reason')}")

    print("6. Settling orders ...")
    settled = _settle_active_orders(pipeline, poll=not dry_run)
    for s in settled:
        _log_session(root, "order_status", **{k: v for k, v in s.items() if k != "error"})
        status_line = s.get("broker_status") or s.get("error") or s.get("status")
        print(f"   [order] {s.get('symbol')} {s.get('side')} → {s.get('status')} "
              f"(broker={status_line}, filled={s.get('filled_quantity')})")
    report["orders_settled"] = settled

    orders = pipeline.order_manager.all_orders()
    report["orders_count"] = len(orders)
    report["status"] = "completed"
    report["equity"] = report["process_result"]["equity"]
    report["positions"] = result["positions"]
    _log_session(root, "session_end", status="completed",
                 equity=report["equity"], orders=sorted(
                     f"{o.side.value}:{o.status.value}" for o in orders))
    return report


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    load_dotenv()

    report: Dict[str, Any] = {
        "title": "US Paper Daily Session — USTrendFollowStrategy (Alpaca paper)",
        "generated_at": _utc_now().isoformat(),
        "session_date": _session_date(),
        "status": "running",
    }

    try:
        opts = _parse_args(sys.argv[1:])
    except ValueError as exc:
        print(f"[error] {exc}")
        sys.exit(1)
    report["symbols"] = opts["symbols"]
    report["mode"] = opts["mode"]
    _log_session(opts["data_dir"], "session_start", mode=opts["mode"], symbols=opts["symbols"])

    # 1. Dependency check.
    try:
        import alpaca  # noqa: F401
    except ImportError:
        report["status"] = "missing_dependency"
        print("[skip] alpaca-py is not installed. Install it with: .venv/bin/pip install 'alpaca-py>=0.21'")
        _log_session(opts["data_dir"], "session_end", status="missing_dependency")
        print(f"Report: {_save_report(report, opts['data_dir'])}")
        sys.exit(2)

    # 2. Credential check.
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret_key:
        report["status"] = "missing_credentials"
        print("[skip] ALPACA_API_KEY / ALPACA_SECRET_KEY are not configured (paper account).")
        _log_session(opts["data_dir"], "session_end", status="missing_credentials")
        print(f"Report: {_save_report(report, opts['data_dir'])}")
        sys.exit(0)

    mode = opts["mode"]

    if mode == MODE_SMOKE:
        run_smoke(opts, report)
    else:
        if mode == MODE_AUTO:
            wait = _preclose_wait_seconds(_et_now())
            if wait is None:
                report["status"] = "market_closed"
                report["reason"] = "Weekend — no US equity trading session."
                print("[skip] Weekend — no US equity trading session.")
                _log_session(opts["data_dir"], "session_end", status="market_closed")
                print(f"Report: {_save_report(report, opts['data_dir'])}")
                sys.exit(0)
            if wait > 0:
                target = (_utc_now() + timedelta(seconds=wait)).isoformat()
                print(f"[wait] Outside the pre-close window — sleeping until ~{target} "
                      f"(15:30 ET).")
                _sleep.sleep(wait)
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
