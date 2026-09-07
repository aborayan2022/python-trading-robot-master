"""US strategy paper smoke — USTrendFollowStrategy through the real Alpaca paper pipeline.

This is a wiring/integration smoke test, NOT an economic measurement:

  * It builds the exact production paper pipeline (``build_alpaca_pipeline``):
    AlpacaBroker (paper) + AlpacaDataProvider + the trend-follow strategy +
    conservative risk limits + audit ledger + runtime metrics.
  * It polls the live Alpaca data feed for a short bounded number of minute
    bars and drives them through the real TradingLoop.
  * It is intentionally bounded (default 30 bars @ 3s) so it can be scheduled.

What it proves:
  - Alpaca credentials authenticate against the paper account.
  - The live data feed returns normalized bars for the universe.
  - The strategy runs inside the real runtime on real data without crashing.
  - Audit/metrics recording and a disk-backed report round-trip work.

What it does NOT prove (honesty notes written into the report):
  - Trade economics. Day-scale trend strategies legitimately emit HOLD on a
    few minute bars, so typically zero orders fire here.
  - Signal quality — see ``us_strategy_backtest.py`` for the cost-adjusted
    daily backtest.

Graceful degradations (all exit 0 with a JSON report, never crash):
  - Missing ``alpaca-py`` dependency        -> status "missing_dependency"  (exit 2)
  - Missing ALPACA_API_KEY / ALPACA_SECRET_KEY -> status "missing_credentials"
  - Outside the US regular session          -> status "market_closed" (no API calls)

Environment / CLI:
    PYROBOT_SYMBOLS | --symbols   comma-separated universe  (default AAPL,MSFT,NVDA)
    --bars                          number of polls          (default 30)
    --interval                      seconds between polls    (default 3.0)
    PYROBOT_DATA_DIR               report/audit/metrics root override (default .)

Run:  .venv/bin/python us_strategy_paper_smoke.py [--bars 40] [--interval 2.0]
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from pyrobot.data.alpaca import AlpacaDataProvider, is_us_equity_session
from pyrobot.runtime.loop import (
    TradingLoop,
    alpaca_polling_provider,
    build_alpaca_pipeline,
)
from pyrobot.strategies.us_trend import USTrendFollowStrategy

ROOT = Path(os.environ.get("PYROBOT_DATA_DIR", ".")).resolve()
REPORTS_DIR = ROOT / "data" / "reports"
AUDIT_DIR = ROOT / "data" / "audit"
METRICS_DIR = ROOT / "data" / "metrics"

DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA"]


def _parse_args(argv: List[str]) -> Dict[str, Any]:
    symbols = [s.strip().upper() for s in os.environ.get("PYROBOT_SYMBOLS", ",".join(DEFAULT_UNIVERSE)).split(",") if s.strip()]
    bars = 30
    interval = 3.0
    i = 0
    while i < len(argv):
        if argv[i] == "--bars" and i + 1 < len(argv):
            bars = int(argv[i + 1])
            i += 2
        elif argv[i] == "--interval" and i + 1 < len(argv):
            interval = float(argv[i + 1])
            i += 2
        elif argv[i] == "--symbols" and i + 1 < len(argv):
            symbols = [s.strip().upper() for s in argv[i + 1].split(",") if s.strip()]
            i += 2
        else:
            i += 1
    return {"symbols": symbols or DEFAULT_UNIVERSE, "bars": max(1, bars), "interval": max(0.0, interval)}


def _save_report(payload: Dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"us_strategy_paper_smoke_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out


def main() -> None:
    load_dotenv()
    opts = _parse_args(sys.argv[1:])
    symbols = opts["symbols"]
    bars = opts["bars"]
    interval = opts["interval"]

    ts = datetime.now(timezone.utc).isoformat()
    report: Dict[str, Any] = {
        "title": "US Strategy Paper Smoke — USTrendFollowStrategy (Alpaca paper)",
        "generated_at": ts,
        "symbols": symbols,
        "bars_max": bars,
        "bar_interval_seconds": interval,
        "status": "running",
        "honesty_notes": [
            "Wiring smoke only: day-scale trend strategies legitimately emit HOLD on a handful "
            "of minute bars, so zero orders is a PASS here, not a failure.",
            "Trade economics and signal quality are measured in us_strategy_backtest.py "
            "(cost-adjusted next-bar-open daily backtest), not here.",
            "Paper positions carry no sector metadata, so the risk manager buckets all longs "
            "under 'UNKNOWN'; the conservative 15% UNKNOWN-sector limit caps concurrent entries.",
        ],
    }

    # 1. Dependency check.
    try:
        import alpaca  # noqa: F401
    except ImportError:
        report["status"] = "missing_dependency"
        print("[skip] alpaca-py is not installed. Install it with: .venv/bin/pip install 'alpaca-py>=0.21'")
        print(f"Report: {_save_report(report)}")
        sys.exit(2)

    # 2. Credential check.
    api_key = os.environ.get("ALPACA_API_KEY", "")
    secret_key = os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret_key:
        report["status"] = "missing_credentials"
        print("[skip] ALPACA_API_KEY / ALPACA_SECRET_KEY are not configured (paper account).")
        print(f"Report: {_save_report(report)}")
        sys.exit(0)

    # 3. Market-session gate (no API calls needed when closed → graceful skip).
    if not is_us_equity_session():
        report["status"] = "market_closed"
        print("[skip] US equity market is outside the regular session (09:30-16:00 ET, weekdays).")
        print(f"Report: {_save_report(report)}")
        sys.exit(0)

    audit_path = str(AUDIT_DIR / "us_strategy_paper_smoke.jsonl")
    metrics_path = str(METRICS_DIR / "us_strategy_paper_smoke.jsonl")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    from pyrobot.monitoring import RuntimeMetrics

    strategy = USTrendFollowStrategy(strategy_id="us_trend_follow", symbols=symbols)
    pipeline = build_alpaca_pipeline(
        symbols=symbols,
        profile="alpaca_paper",
        audit_path=audit_path,
        strategy=strategy,
    )
    data_provider = AlpacaDataProvider()
    provider = alpaca_polling_provider(data_provider, symbols)

    print("=" * 72)
    print("PyRobot — US Strategy Paper Smoke (Alpaca paper, real data feed)")
    print("=" * 72)
    print(f"Universe: {', '.join(symbols)} | bars: {bars} | interval: {interval}s")
    print(f"Audit: {audit_path}")
    print("Note: strategy needs day-scale history; a HOLD-only smoke is a PASS.\n")

    # 4. Data-connectivity probe (independent of the trading loop).
    print("1. Data-connectivity probe (latest 5 daily bars per symbol) ...")
    probe: Dict[str, List[Dict[str, Any]]] = {}
    from datetime import timedelta

    from pyrobot.data.base import DataFrequency

    try:
        for sym in symbols:
            candles = data_provider.get_historical_candles(
                symbol=sym,
                start=datetime.now(timezone.utc) - timedelta(days=10),
                end=datetime.now(timezone.utc),
                frequency=DataFrequency.DAILY,
            )
            probe[sym] = [
                {"date": c.timestamp.isoformat(), "close": c.close, "volume": c.volume}
                for c in candles[-5:]
            ]
            print(f"   {sym}: {len(candles)} daily candles (last: {probe[sym][-1]['date']})")
    except Exception as exc:
        report["status"] = "data_probe_failed"
        report["data_probe_error"] = str(exc)
        print(f"   [fail] daily probe failed for some symbols: {exc}")

    # 5. Bounded live loop through the real runtime.
    print(f"\n2. Running TradingLoop (up to {bars} minute-bar polls) ...")
    metrics = RuntimeMetrics(output_path=metrics_path)
    loop = TradingLoop(
        pipeline=pipeline,
        bar_provider=provider,
        bar_interval=interval,
        max_bars=bars,
        metrics=metrics,
    )
    started = time.time()
    try:
        result = loop.run()
        elapsed = time.time() - started
        print(f"   Loop finished: {result.get('bars_processed')} bars in {elapsed:.1f}s")

        status = result.get("status", {})
        orders = pipeline.order_manager.all_orders()
        fills = [o for o in orders if o.status.value == "FILLED"]
        news = [o for o in orders if o.status.value == "NEW"]
        account = pipeline.broker.get_account_info()
        positions = pipeline.broker.get_positions()

        report.update({
            "status": "completed",
            "bars_processed": result.get("bars_processed"),
            "elapsed_seconds": round(elapsed, 2),
            "audit_path": audit_path,
            "metrics_path": metrics_path,
            "account": account,
            "positions": positions,
            "orders_count": len(orders),
            "filled_orders": len(fills),
            "unfilled_new_orders": len(news),
            "kill_switch_active": bool(status.get("kill_switch_active", False)),
            "data_probe": probe,
        })

        print(f"   Account: cash=${account.get('cash_balance', 0):,.2f} "
              f"buying_power=${account.get('buying_power', 0):,.2f}")
        print(f"   Positions: {positions}")
        print(f"   Orders: {len(orders)} (filled={len(fills)}, new={len(news)})")
        print(f"   Kill switch active: {report['kill_switch_active']}")
        print("\n   Summary: strategy ran end-to-end on the real Alpaca paper feed. "
              "A HOLD-only run is expected and is a PASS for a wiring smoke.")
    except Exception as exc:
        report["status"] = "error"
        report["error"] = str(exc)
        print(f"   [fail] smoke errored: {exc}")

    out = _save_report(report)
    print(f"\nReport: {out}")
    print("Done.")


if __name__ == "__main__":
    main()
