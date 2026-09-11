"""US market trading test — honest cost-adjusted backtest of USTrendFollowStrategy.

This script exercises the initial trading strategy against real 5-year daily
US large-cap data (yfinance, cached in data/us_market/) in two complementary
ways:

1. Honest backtest (primary): per-symbol signals from USTrendFollowStrategy,
   filled at the NEXT bar's open through the ExecutionCostModel (spread,
   slippage, market impact, volume participation, commissions, SEC fees).
   This is the same-bar-decision / next-bar-open honesty contract enforced by
   the BacktestEngine tests.

2. Runtime replay (integration proof): the same strategy driven through the
   real TradingPipeline + TradingLoop (the exact path the management console
   uses), recording fills, positions and equity. NOTE: the paper broker fills
   at the bar's close with no modeled costs, so this is not the economic
   measurement — it proves the strategy operates end-to-end in the runtime.

A Buy & Hold equal-weight benchmark with the same cost model is computed for
comparison. Results are written to data/reports/us_strategy_backtest_<ts>.json
and can be viewed in the console's Reports tab.

Environment:
    PYROBOT_DATA_DIR     cache/report root override (default .)
    PYROBOT_YEARS        years of daily data (default 5)
    PYROBOT_UNIVERSE     comma-separated symbols (default the 10 symbols below)

Run:  .venv/bin/python us_strategy_backtest.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from pyrobot.backtesting.cost_model import ExecutionCostModel
from pyrobot.backtesting.runner import _git_provenance
from pyrobot.runtime.loop import (
    TradingLoop,
    build_default_pipeline,
    replay_provider,
)
from pyrobot.runtime.pipeline import _as_stock_frame
from pyrobot.strategies.us_trend import USTrendFollowStrategy

ROOT = Path(os.environ.get("PYROBOT_DATA_DIR", ".")).resolve()
DATA_DIR = ROOT / "data" / "us_market"
REPORTS_DIR = ROOT / "data" / "reports"

DEFAULT_UNIVERSE = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "XOM", "JNJ", "WMT"]
INITIAL_BALANCE = 100_000.0
MAX_POSITION_FRACTION = 0.12   # risk-limit-style cap per position (12% of equity)
HISTORY_WINDOW = 300           # mirrors TradingPipeline.history_window


# ── Data acquisition (yfinance, CSV cache) ────────────────────────────────────


def fetch_symbol(symbol: str, years: int) -> pd.DataFrame:
    """Download daily OHLCV for one symbol, returning rows for the shared pipeline."""
    import yfinance as yf  # local import: only required when downloading

    raw = yf.Ticker(symbol).history(period=f"{years}y", interval="1d", auto_adjust=True)
    if raw.empty:
        raise RuntimeError(f"No data returned by Yahoo Finance for {symbol}")
    df = pd.DataFrame({
        "open": raw["Open"].astype(float),
        "high": raw["High"].astype(float),
        "low": raw["Low"].astype(float),
        "close": raw["Close"].astype(float),
        "volume": raw["Volume"].astype(float),
    })
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "datetime"
    df["symbol"] = symbol
    return df


def load_or_download(symbols: List[str], years: int, refresh: bool = False) -> Dict[str, pd.DataFrame]:
    """Load cached CSVs or download them (caches into data/us_market/)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frames: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        cache = DATA_DIR / f"{sym}.csv"
        if cache.exists() and not refresh:
            df = pd.read_csv(cache, parse_dates=["datetime"], index_col="datetime")
            df = df.tz_localize("UTC") if df.index.tz is None else df
            frames[sym] = df
            print(f"  cached {sym}: {len(df)} rows ({df.index[0].date()} → {df.index[-1].date()})")
            continue
        print(f"  downloading {sym} ...")
        try:
            df = fetch_symbol(sym, years)
        except Exception as exc:
            print(f"  ⚠ {sym}: download failed ({exc}) — skipping")
            continue
        df.to_csv(cache)
        frames[sym] = df
        print(f"  saved {sym}: {len(df)} rows ({df.index[0].date()} → {df.index[-1].date()})")
    if not frames:
        raise SystemExit("No data available — check network or the data/us_market cache.")
    return frames


def build_bar_series(frames: Dict[str, pd.DataFrame]) -> List[Dict[str, dict]]:
    """Align per-day rows into {symbol: bar} bars for the TradingLoop replay."""
    aligned: Dict[Any, Dict[str, dict]] = {}
    for sym, df in frames.items():
        for ts, row in df.iterrows():
            aligned.setdefault(ts, {})[sym] = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "datetime": ts,
            }
    ordered = [aligned[ts] for ts in sorted(aligned) if aligned[ts]]
    return ordered


# ── Honest cost-adjusted per-symbol backtest ───────────────────────────────────


def honest_backtest(
    frames: Dict[str, pd.DataFrame],
    cost_model: ExecutionCostModel,
) -> Dict[str, Any]:
    """Same-bar decision, next-bar-open fills through the cost model."""
    symbols = list(frames.keys())
    timestamps = sorted({ts for s in symbols for ts in frames[s].index})
    timestamps = [ts for ts in timestamps if any(ts in frames[s].index for s in symbols)]

    strategy = USTrendFollowStrategy(strategy_id="us_trend_follow", symbols=symbols)
    strategy.initialize()

    cash = INITIAL_BALANCE
    positions: Dict[str, Dict[str, Any]] = {}     # symbol → qty, avg price, entry_ts
    entry_fees: Dict[str, float] = {}
    pending: List[Dict[str, Any]] = []               # fills for this bar's open
    trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []

    history: Dict[str, List[dict]] = {s: [] for s in symbols}

    for bar_idx, ts in enumerate(timestamps):
        row_by_sym: Dict[str, dict] = {}
        for sym in symbols:
            row = frames[sym].loc[ts]
            row_by_sym[sym] = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
                "datetime": ts,
            }

        # 1. Fill pending orders at today's open (decisions from yesterday).
        still_pending: List[Dict[str, Any]] = []
        for order in pending:
            sym = order["symbol"]
            row = row_by_sym.get(sym)
            if row is None:
                still_pending.append(order)
                continue
            cash = _fill(
                order, row, cost_model, cash, positions, entry_fees,
                trades, still_pending, ts, strategy,
            )
        pending = still_pending

        # 2. Mark-to-market equity at today's close.
        eq = cash + sum(
            positions[s]["quantity"] * row_by_sym[s]["close"]
            for s in positions if s in row_by_sym
        ) if positions else cash
        equity_curve.append({
            "timestamp": ts.isoformat(),
            "equity": round(float(eq), 2),
            "cash": round(float(cash), 2),
            "positions": {s: round(p["quantity"], 2) for s, p in positions.items()},
        })

        # 3. Decide for the NEXT bar (strategy sees the rolling window the
        # pipeline would have given it — mirrors TradingPipeline.history_window).
        for sym in symbols:
            history[sym].append(row_by_sym[sym])
            window = history[sym][-HISTORY_WINDOW:]
            frame = pd.DataFrame(window)
            stock_frame = _as_stock_frame(frame, sym)
            signal = strategy.on_bar(sym, row_by_sym[sym], stock_frame)

            if signal.action.value == "BUY" and sym not in positions:
                price_now = row_by_sym[sym]["close"]
                qty = int((eq * MAX_POSITION_FRACTION) / price_now) if price_now > 0 else 0
                if qty > 0:
                    pending.append({"symbol": sym, "side": "BUY", "quantity": qty})
            elif signal.action.value == "SELL" and sym in positions:
                pending.append({
                    "symbol": sym, "side": "SELL", "quantity": positions[sym]["quantity"],
                })

    final_close = {sym: frames[sym].iloc[-1]["close"] for sym in symbols}
    ending_equity = cash + sum(
        positions[s]["quantity"] * final_close[s] for s in positions if s in final_close
    )
    if positions:
        equity_curve.append({
            "timestamp": timestamps[-1].isoformat(),
            "equity": round(float(ending_equity), 2),
            "cash": round(cash, 2),
            "positions": {s: round(p["quantity"], 2) for s, p in positions.items()},
            "markout": True,
        })

    summary = _metrics_from_curve(equity_curve, trades, "honest (next-bar open + costs)")
    return {
        "mode": "honest",
        "bars": len(timestamps),
        "start": timestamps[0].isoformat(),
        "end": timestamps[-1].isoformat(),
        "equity_curve": equity_curve,
        "trades": trades,
        "summary": summary,
    }


def _fill(order, row, cost_model, cash, positions: Dict[str, Dict[str, Any]], entry_fees, trades, still_pending, ts, strategy):
    """Execute one order at the bar's open through the cost model."""
    sym, side, qty = order["symbol"], order["side"], int(order["quantity"])
    open_price = float(row["open"])
    if open_price <= 0:
        still_pending.append(order)
        return cash

    volatility = abs(float(row["high"]) - float(row["low"])) / open_price if open_price else 0.015
    fill = cost_model.calculate_fill(
        side=side, quantity=float(qty), price=open_price,
        bar_volume=float(row["volume"]), volatility=volatility,
        enforce_participation=(side == "BUY"),
    )
    filled = int(fill["filled_qty"])
    fees = float(fill["total_commission"]) + float(fill["sec_fee"])
    fill_price = float(fill["fill_price"])
    if filled <= 0:
        return cash

    if side == "BUY":
        cost = filled * fill_price + fees
        if cost > cash:
            filled = int(cash / (fill_price * (1 + 1e-9)))
            if filled <= 0:
                return cash
            cost = filled * fill_price + fees
        cash -= cost
        if sym in positions:
            existing = positions[sym]
            total_qty = existing["quantity"] + filled
            existing["avg_price"] = (
                (existing["avg_price"] * existing["quantity"]) + fill_price * filled
            ) / total_qty
            existing["quantity"] = total_qty
        else:
            positions[sym] = {"quantity": float(filled), "avg_price": fill_price, "entry_ts": str(ts)}
            entry_fees[sym] = fees
        if filled < qty:
            still_pending.append({"symbol": sym, "side": side, "quantity": qty - filled})
        # Realize the fill for the strategy's holding tracker.
        strategy.on_order_fill({"symbol": sym, "quantity": filled})
    else:
        position = positions.get(sym)
        if position is None:
            return cash
        sell_qty = min(filled, int(position["quantity"]))
        proceeds = sell_qty * fill_price - fees
        cash += proceeds
        gross = (fill_price - position["avg_price"]) * sell_qty
        net_pnl = gross - fees - entry_fees.get(sym, 0.0)
        trades.append({
            "symbol": sym,
            "side": "SELL",
            "entry_price": round(position["avg_price"], 4),
            "exit_price": round(fill_price, 4),
            "quantity": sell_qty,
            "pnl": round(net_pnl, 2),
            "fees": round(fees + entry_fees.get(sym, 0.0), 4),
            "entry_ts": position.get("entry_ts", ""),
            "exit_ts": str(ts),
        })
        position["quantity"] -= sell_qty
        if position["quantity"] <= 0:
            del positions[sym]
            entry_fees.pop(sym, None)
        strategy.on_order_fill({"symbol": sym, "quantity": sell_qty})
    return cash


def _metrics_from_curve(equity_curve: List[Dict[str, Any]], trades: List[dict], label: str) -> Dict[str, Any]:
    equities = [float(p["equity"]) for p in equity_curve]
    if not equities:
        return {"label": label, "available": False}
    final = equities[-1]
    total_return = (final - INITIAL_BALANCE) / INITIAL_BALANCE * 100.0
    daily = pd.Series(equities).pct_change().dropna()
    sharpe = float(np.mean(daily) / np.std(daily) * np.sqrt(252)) if len(daily) > 1 and np.std(daily) > 0 else 0.0
    peak = np.maximum.accumulate(equities)
    dd = np.min((np.array(equities) - peak) / peak)
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    return {
        "label": label,
        "available": True,
        "starting_balance": INITIAL_BALANCE,
        "ending_balance": round(final, 2),
        "total_return_pct": round(total_return, 2),
        "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown_pct": round(float(dd) * 100.0, 2),
        "total_trades": len(trades),
        "winning_trades": len(wins),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
    }


# ── Buy & Hold benchmark (same cost model) ─────────────────────────────────────


def buy_and_hold_benchmark(frames: Dict[str, pd.DataFrame], cost_model: ExecutionCostModel) -> Dict[str, Any]:
    symbols = list(frames.keys())
    first_ts = min(frames[s].index[0] for s in symbols)
    last_ts = max(frames[s].index[-1] for s in symbols)
    timestamps = sorted({ts for s in symbols for ts in frames[s].index if first_ts <= ts <= last_ts})

    cash = INITIAL_BALANCE
    positions: Dict[str, Dict[str, float]] = {}
    entry_fees: Dict[str, float] = {}
    curve: List[Dict[str, Any]] = []

    for idx, ts in enumerate(timestamps):
        closes = {s: frames[s].loc[ts]["close"] for s in symbols if ts in frames[s].index}
        opens = {s: frames[s].loc[ts]["open"] for s in symbols if ts in frames[s].index}

        if idx == 0:
            per = INITIAL_BALANCE / len(symbols)
            for sym in symbols:
                price = opens.get(sym, closes.get(sym))
                if price is None or price <= 0:
                    continue
                qty = int(per / price)
                if qty <= 0:
                    continue
                fill = cost_model.calculate_fill(
                    side="BUY", quantity=float(qty), price=price,
                    bar_volume=float(frames[sym].loc[ts]["volume"]), volatility=0.02,
                    enforce_participation=True,
                )
                filled = int(fill["filled_qty"])
                if filled <= 0:
                    continue
                fees = float(fill["total_commission"]) + float(fill["sec_fee"])
                cost = filled * float(fill["fill_price"]) + fees
                if cost > cash:
                    filled = int(cash / (float(fill["fill_price"]) * (1 + 1e-9)))
                    cost = filled * float(fill["fill_price"]) + fees
                cash -= cost
                positions[sym] = {"quantity": float(filled), "avg_price": float(fill["fill_price"])}
                entry_fees[sym] = fees

        equity = cash + sum(positions[s]["quantity"] * closes.get(s, positions[s]["avg_price"]) for s in positions)
        curve.append({"timestamp": ts.isoformat(), "equity": round(float(equity), 2)})

    return {"mode": "buy_and_hold", "start": first_ts.isoformat(), "end": last_ts.isoformat(), "equity_curve": curve}


# ── Runtime replay via the real pipeline (integration proof) ───────────────────


def runtime_replay(bars: List[Dict[str, dict]]) -> Dict[str, Any]:
    symbols = sorted(bars[0].keys()) if bars else []
    strategy = USTrendFollowStrategy(strategy_id="us_trend_follow", symbols=symbols)
    pipeline = build_default_pipeline(
        symbols=symbols, initial_balance=INITIAL_BALANCE, strategy=strategy,
    )
    loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(bars), bar_interval=0.0)
    result = loop.run()
    orders = pipeline.order_manager.all_orders()
    fills = [o for o in orders if o.status.value == "FILLED"]
    news = [o for o in orders if o.status.value == "NEW"]
    info = pipeline.broker.get_account_info()
    return {
        "mode": "runtime_replay_pipeline",
        "bars_processed": result.get("bars_processed"),
        "orders": len(orders),
        "filled_orders": len(fills),
        "unfilled_new_orders": len(news),
        "ending_equity": round(float(info.get("equity", 0.0)), 2),
        "positions": pipeline.broker.get_positions(),
        "kill_switch_active": bool(result.get("status", {}).get("kill_switch_active", False)),
        "note": "Integration proof only — the paper broker fills at the bar close with "
                "no modeled costs, so equity here is not an economic result. The replay "
                "exercises the FULL production risk gates: BUY orders that breach the "
                "risk manager's 25% UNKNOWN-sector exposure limit are rejected and "
                "remain registered as NEW (never marked REJECTED), so in churn-heavy "
                "multisymbol runs the OrderManager's 500-active-order cap can eventually "
                "block further trading and a max-drawdown kill switch can halt the loop. "
                "Both are real platform behaviors surfaced by this test — the honest "
                "backtest above is the cost-adjusted economic measurement.",
    }


# ── Report assembly ────────────────────────────────────────────────────────────


def main() -> None:
    years = int(os.environ.get("PYROBOT_YEARS", "5"))
    symbols = [s.strip().upper() for s in os.environ.get("PYROBOT_UNIVERSE", ",".join(DEFAULT_UNIVERSE)).split(",") if s.strip()]
    refresh = "--refresh" in sys.argv

    print("=" * 72)
    print("PyRobot — US Market Trading Test (trend-follow strategy)")
    print("=" * 72)
    print(f"Universe ({len(symbols)}): {', '.join(symbols)}")
    print(f"History: {years}y daily (yfinance, cached in {DATA_DIR})")
    print(f"Starting balance: ${INITIAL_BALANCE:,.0f}")

    print("\n1. Fetching / loading market data ...")
    t0 = time.time()
    frames = load_or_download(symbols, years, refresh=refresh)
    if len(frames) < len(symbols):
        print(f"   Skipped {len(symbols) - len(frames)} symbols (data unavailable).")
    symbols = list(frames.keys())

    bars = build_bar_series(frames)
    print(f"   Aligned {len(bars)} daily bars across {len(symbols)} symbols in {time.time() - t0:.1f}s")

    cost_model = ExecutionCostModel()

    print("\n2. Honest backtest (same-bar decision → next-bar open fills + costs) ...")
    honest = honest_backtest(frames, cost_model)
    s = honest["summary"]
    print(f"   {s['label']}: return={s['total_return_pct']}% sharpe={s['sharpe_ratio']} "
          f"maxDD={s['max_drawdown_pct']}% trades={s['total_trades']} win_rate={s['win_rate_pct']}%")

    print("\n3. Runtime replay through the real pipeline (integration proof) ...")
    replay = runtime_replay(bars)
    print(f"   bars={replay['bars_processed']} orders={replay['orders']} "
          f"filled={replay['filled_orders']} ending_equity=${replay['ending_equity']:,.2f}")

    print("\n4. Buy & Hold benchmark (equal weight, same cost model) ...")
    bh = buy_and_hold_benchmark(frames, cost_model)
    bh_curve = bh["equity_curve"]
    bh_summary = _metrics_from_curve(bh_curve, [], "buy_and_hold")
    print(f"   Return: {bh_summary['total_return_pct']}% (no drawdown/win-rate published — equity curve only)")

    report = {
        "title": "US Market Trading Test — USTrendFollowStrategy",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": _git_provenance(),
        "universe_universe": symbols,
        "symbols": symbols,
        "strategy": "USTrendFollowStrategy",
        "strategy_description": "Long-only trend (+200D SMA) + momentum (EMA21>EMA50) + "
                                "RSI(14) band + ATR% filter; exits on RSI>=70, close<EMA50, trailing stop.",
        "starting_balance": INITIAL_BALANCE,
        "period": {"start": honest["start"], "end": honest["end"], "bars": honest["bars"]},
        "honesty_notes": [
            "Signals are decided on bar t close and filled at bar t+1 open — no same-bar lookahead.",
            "All fills pass through ExecutionCostModel (spread, slippage, sqrt market impact, "
            "volume participation, commission, SEC fees).",
            "The runtime_replay section is integration proof only: the paper broker fills at bar "
            "close with no modeled costs, so its equity is not an economic result.",
            "Universe symbols with unavailable data are excluded and reported under 'symbols'.",
            "Platform findings surfaced by this test (for the repair backlog): (1) risk-rejected "
            "orders stay registered as NEW instead of REJECTED, so they count as active and can "
            "eventually trip the OrderManager 500-active-order cap; (2) paper positions carry no "
            "sector metadata, so the risk manager buckets all paper longs under 'UNKNOWN' and the "
            "25% UNKNOWN-sector limit caps real-money-style scaling in multisymbol runs.",
        ],
        "honest_backtest": honest,
        "buy_and_hold": {"summary": bh_summary, "equity_curve": bh_curve},
        "runtime_replay": replay,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"us_strategy_backtest_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\n5. Comparison (honest vs buy & hold):")
    print(f"   Strategy return: {s['total_return_pct']}%  |  Buy & Hold return: {bh_summary['total_return_pct']}%")
    print(f"   Report saved to: {out_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
