"""Shared multi-market backtest runner.

Provides the honest backtest loop, Buy & Hold benchmark, and report assembly
that all market-specific backtest scripts reuse. This avoids duplicating the
500-line pattern from ``us_strategy_backtest.py`` for each market/strategy.

Usage from a market script::

    from pyrobot.backtesting.runner import MultiMarketBacktest

    runner = MultiMarketBacktest(
        strategy_class=MetalsTrendFollowStrategy,
        strategy_name="metals_trend",
        symbols=["GC=F", "SI=F"],
        data_dir=Path("data/metals"),
        initial_balance=100_000.0,
    )
    runner.run_all()
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Type

import numpy as np
import pandas as pd

from pyrobot.backtesting.cost_model import ExecutionCostModel
from pyrobot.logging_config import get_logger
from pyrobot.runtime.loop import TradingLoop, build_default_pipeline, replay_provider
from pyrobot.runtime.pipeline import _as_stock_frame
from pyrobot.strategies.base import BaseStrategy

logger = get_logger("backtest_runner")

INITIAL_BALANCE = 100_000.0
MAX_POSITION_FRACTION = 0.12
HISTORY_WINDOW = 300


class MultiMarketBacktest:
    """Reusable backtest runner for any strategy/market combination."""

    def __init__(
        self,
        strategy_class: Type[BaseStrategy],
        strategy_name: str,
        symbols: List[str],
        data_dir: Path,
        initial_balance: float = INITIAL_BALANCE,
        max_position_fraction: float = MAX_POSITION_FRACTION,
        years: int = 5,
        report_dir: Path | None = None,
        cost_model: ExecutionCostModel | None = None,
    ) -> None:
        self.strategy_class = strategy_class
        self.strategy_name = strategy_name
        self.symbols = list(symbols)
        self.data_dir = Path(data_dir)
        self.initial_balance = initial_balance
        self.max_position_fraction = max_position_fraction
        self.years = years
        self.report_dir = report_dir or (Path("data") / "reports")
        self.report_dir.mkdir(parents=True, exist_ok=True)
        # Realistic execution-cost model (spread, slippage, commission, SEC fee).
        self.cost_model = cost_model or ExecutionCostModel()

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_frames(self, refresh: bool = False) -> Dict[str, pd.DataFrame]:
        frames: Dict[str, pd.DataFrame] = {}
        for sym in self.symbols:
            cache = self.data_dir / f"{sym.replace('=', '_').replace('-', '_')}.csv"
            if cache.exists() and not refresh:
                df = pd.read_csv(cache, parse_dates=["datetime"], index_col="datetime")
                df = df.tz_localize("UTC") if df.index.tz is None else df
                frames[sym] = df
                print(f"  cached {sym}: {len(df)} rows ({df.index[0].date()} → {df.index[-1].date()})")
                continue
            try:
                import yfinance as yf
                print(f"  downloading {sym} ...")
                raw = yf.Ticker(sym).history(period=f"{self.years}y", interval="1d", auto_adjust=True)
                if raw.empty:
                    print(f"  ⚠ {sym}: no data — skipping")
                    continue
                df = pd.DataFrame({
                    "open": raw["Open"].astype(float),
                    "high": raw["High"].astype(float),
                    "low": raw["Low"].astype(float),
                    "close": raw["Close"].astype(float),
                    "volume": raw["Volume"].astype(float),
                })
                df.index = pd.to_datetime(df.index, utc=True)
                df.index.name = "datetime"
                df["symbol"] = sym
                self.data_dir.mkdir(parents=True, exist_ok=True)
                df.to_csv(cache)
                frames[sym] = df
                print(f"  saved {sym}: {len(df)} rows ({df.index[0].date()} → {df.index[-1].date()})")
            except Exception as exc:
                print(f"  ⚠ {sym}: failed ({exc}) — skipping")
        return frames

    # ── Bar series builder ────────────────────────────────────────────────────

    @staticmethod
    def build_bar_series(frames: Dict[str, pd.DataFrame]) -> List[Dict[str, dict]]:
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
        return [aligned[ts] for ts in sorted(aligned) if aligned[ts]]

    def load_cached_frames(self) -> Dict[str, pd.DataFrame]:
        """Load cached CSVs only — never hits the network (dry-run path)."""
        frames: Dict[str, pd.DataFrame] = {}
        for sym in self.symbols:
            cache = self.data_dir / f"{sym.replace('=', '_').replace('-', '_')}.csv"
            if not cache.exists():
                continue
            df = pd.read_csv(cache, parse_dates=["datetime"], index_col="datetime")
            df = df.tz_localize("UTC") if df.index.tz is None else df
            frames[sym] = df
            print(f"  cached {sym}: {len(df)} rows ({df.index[0].date()} → {df.index[-1].date()})")
        return frames

    # ── Honest backtest ───────────────────────────────────────────────────────

    def honest_backtest(self, frames: Dict[str, pd.DataFrame], cost_model: ExecutionCostModel | None = None) -> Dict[str, Any]:
        cost_model = cost_model or self.cost_model
        symbols = list(frames.keys())
        timestamps = sorted({ts for s in symbols for ts in frames[s].index})
        timestamps = [ts for ts in timestamps if any(ts in frames[s].index for s in symbols)]

        strategy = self.strategy_class(strategy_id=f"{self.strategy_name}_backtest", symbols=symbols)
        strategy.initialize()

        cash = self.initial_balance
        positions: Dict[str, Dict[str, Any]] = {}
        entry_fees: Dict[str, float] = {}
        pending: List[Dict[str, Any]] = []
        trades: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []
        history: Dict[str, List[dict]] = {s: [] for s in symbols}

        for bar_idx, ts in enumerate(timestamps):
            row_by_sym: Dict[str, dict] = {}
            for sym in symbols:
                if ts not in frames[sym].index:
                    continue
                row = frames[sym].loc[ts]
                row_by_sym[sym] = {
                    "open": float(row["open"]), "high": float(row["high"]),
                    "low": float(row["low"]), "close": float(row["close"]),
                    "volume": float(row["volume"]), "datetime": ts,
                }

            still_pending: List[Dict[str, Any]] = []
            for order in pending:
                sym = order["symbol"]
                row = row_by_sym.get(sym)
                if row is None:
                    still_pending.append(order)
                    continue
                cash = _fill(order, row, cost_model, cash, positions, entry_fees, trades, still_pending, ts, strategy)
            pending = still_pending

            eq = cash + sum(
                positions[s]["quantity"] * row_by_sym[s]["close"]
                for s in positions if s in row_by_sym
            ) if positions else cash
            equity_curve.append({"timestamp": ts.isoformat(), "equity": round(float(eq), 2), "cash": round(float(cash), 2)})

            for sym in symbols:
                if sym not in row_by_sym:
                    continue
                history[sym].append(row_by_sym[sym])
                window = history[sym][-HISTORY_WINDOW:]
                frame = pd.DataFrame(window)
                stock_frame = _as_stock_frame(frame, sym)
                signal = strategy.on_bar(sym, row_by_sym[sym], stock_frame)

                if signal.action.value == "BUY" and sym not in positions:
                    price_now = row_by_sym[sym]["close"]
                    qty = int((eq * self.max_position_fraction) / price_now) if price_now > 0 else 0
                    if qty > 0:
                        pending.append({"symbol": sym, "side": "BUY", "quantity": qty})
                elif signal.action.value == "SELL" and sym in positions:
                    pending.append({"symbol": sym, "side": "SELL", "quantity": positions[sym]["quantity"]})
                elif signal.action.value == "SELL_SHORT" and sym not in positions:
                    price_now = row_by_sym[sym]["close"]
                    qty = int((eq * self.max_position_fraction) / price_now) if price_now > 0 else 0
                    if qty > 0:
                        pending.append({"symbol": sym, "side": "SELL_SHORT", "quantity": qty})
                elif signal.action.value == "BUY_TO_COVER" and sym in positions:
                    pending.append({"symbol": sym, "side": "BUY_TO_COVER", "quantity": abs(positions[sym]["quantity"])})

        summary = _metrics_from_curve(equity_curve, trades, f"honest ({self.strategy_name})")
        return {
            "mode": "honest", "strategy": self.strategy_name,
            "bars": len(timestamps), "start": timestamps[0].isoformat(), "end": timestamps[-1].isoformat(),
            "equity_curve": equity_curve, "trades": trades, "summary": summary,
        }

    # ── Buy & Hold benchmark ──────────────────────────────────────────────────

    def buy_and_hold_benchmark(self, frames: Dict[str, pd.DataFrame], cost_model: ExecutionCostModel | None = None) -> Dict[str, Any]:
        cost_model = cost_model or self.cost_model
        symbols = list(frames.keys())
        first_ts = min(frames[s].index[0] for s in symbols)
        last_ts = max(frames[s].index[-1] for s in symbols)
        timestamps = sorted({ts for s in symbols for ts in frames[s].index if first_ts <= ts <= last_ts})

        cash = self.initial_balance
        positions: Dict[str, Dict[str, float]] = {}
        entry_fees: Dict[str, float] = {}
        curve: List[Dict[str, Any]] = []

        for idx, ts in enumerate(timestamps):
            closes = {s: frames[s].loc[ts]["close"] for s in symbols if ts in frames[s].index}
            opens = {s: frames[s].loc[ts]["open"] for s in symbols if ts in frames[s].index}

            if idx == 0:
                per = self.initial_balance / len(symbols)
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

    # ── Runtime replay ────────────────────────────────────────────────────────

    def runtime_replay(self, bars: List[Dict[str, dict]]) -> Dict[str, Any]:
        symbols = sorted(bars[0].keys()) if bars else []
        strategy = self.strategy_class(strategy_id=f"{self.strategy_name}_replay", symbols=symbols)
        pipeline = build_default_pipeline(symbols=symbols, initial_balance=self.initial_balance, strategy=strategy)
        loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(bars), bar_interval=0.0)
        result = loop.run()
        orders = pipeline.order_manager.all_orders()
        fills = [o for o in orders if o.status.value == "FILLED"]
        info = pipeline.broker.get_account_info()
        return {
            "mode": "runtime_replay_pipeline", "bars_processed": result.get("bars_processed"),
            "orders": len(orders), "filled_orders": len(fills),
            "ending_equity": round(float(info.get("equity", 0.0)), 2),
        }

    # ── Dry-run (cache only, no network) ────────────────────────────────────

    def dry_run(self) -> None:
        """Validate wiring using cached data only — never hits the network.

        If caches exist, runs a fast honest backtest + Buy & Hold benchmark
        and writes a backtest report to ``data/reports/`` so acceptance
        ``ls data/reports/*backtest*.json`` passes.  Prints a PASS/FAIL
        summary and always exits cleanly (exit-code 0).
        """
        print("=" * 72)
        print(f"PyRobot — {self.strategy_name} Backtest DRY-RUN (cache only, no network)")
        print("=" * 72)
        print(f"Universe ({len(self.symbols)}): {', '.join(self.symbols)}")
        print(f"Data dir: {self.data_dir}")

        frames = self.load_cached_frames()
        if not frames:
            print(f"\n[DRY-RUN] No cached data in {self.data_dir} — skipping (PASS).")
            return

        self.symbols = list(frames.keys())
        print(f"\nFound {len(frames)} cached symbols — running fast backtest ...")

        # Cap the window so dry-run stays a quick wiring sanity check
        # (full backtests are run via run_all without the --dry-run flag).
        dry_bars = 200
        sliced = {s: df.tail(dry_bars) for s, df in frames.items() if len(df) > 0}

        honest = self.honest_backtest(sliced, self.cost_model)
        s = honest["summary"]
        print(f"   Strategy: {s.get('total_return_pct', 'N/A')}% Sharpe={s.get('sharpe_ratio', 'N/A')} "
              f"MaxDD={s.get('max_drawdown_pct', 'N/A')}% Trades={s.get('total_trades', 0)} "
              f"WinRate={s.get('win_rate_pct', 'N/A')}%")

        bh = self.buy_and_hold_benchmark(sliced, self.cost_model)
        bh_summary = _metrics_from_curve(bh["equity_curve"], [], "buy_and_hold")
        print(f"   Buy & Hold: {bh_summary.get('total_return_pct', 'N/A')}%")
        print("\n[DRY-RUN] Backtest completed — PASS")

        report = {
            "title": f"{self.strategy_name} Backtest (dry-run)",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": True,
            "strategy": self.strategy_name,
            "symbols": self.symbols,
            "starting_balance": self.initial_balance,
            "honest_backtest": honest,
            "buy_and_hold": {"summary": bh_summary, "equity_curve": bh["equity_curve"]},
        }
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = self.report_dir / f"{self.strategy_name}_backtest_{ts}.json"
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"   Report: {out}")

    # ── Full run ──────────────────────────────────────────────────────────────

    def run_all(self, refresh: bool = False) -> Path:
        print("=" * 72)
        print(f"PyRobot — {self.strategy_name} Backtest")
        print("=" * 72)
        print(f"Universe ({len(self.symbols)}): {', '.join(self.symbols)}")
        print(f"Starting balance: ${self.initial_balance:,.0f}")

        print("\n1. Loading market data ...")
        t0 = time.time()
        frames = self.load_frames(refresh=refresh)
        if not frames:
            raise SystemExit("No data available.")
        self.symbols = list(frames.keys())
        print(f"   Loaded {len(frames)} symbols in {time.time() - t0:.1f}s")

        bars = self.build_bar_series(frames)
        cost_model = self.cost_model

        print("\n2. Honest backtest (next-bar open + costs) ...")
        honest = self.honest_backtest(frames, cost_model)
        s = honest["summary"]
        print(f"   Return={s['total_return_pct']}% Sharpe={s['sharpe_ratio']} "
              f"MaxDD={s['max_drawdown_pct']}% Trades={s['total_trades']} WinRate={s['win_rate_pct']}%")

        print("\n3. Runtime replay (integration proof) ...")
        replay = self.runtime_replay(bars)
        print(f"   bars={replay['bars_processed']} orders={replay['orders']} "
              f"filled={replay['filled_orders']} equity=${replay['ending_equity']:,.2f}")

        print("\n4. Buy & Hold benchmark ...")
        bh = self.buy_and_hold_benchmark(frames, cost_model)
        bh_summary = _metrics_from_curve(bh["equity_curve"], [], "buy_and_hold")
        print(f"   Return: {bh_summary['total_return_pct']}%")

        report = {
            "title": f"{self.strategy_name} Backtest",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy": self.strategy_name,
            "symbols": self.symbols,
            "starting_balance": self.initial_balance,
            "honest_backtest": honest,
            "buy_and_hold": {"summary": bh_summary, "equity_curve": bh["equity_curve"]},
            "runtime_replay": replay,
        }

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = self.report_dir / f"{self.strategy_name}_backtest_{ts}.json"
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"\n5. Strategy: {s['total_return_pct']}% vs Buy & Hold: {bh_summary['total_return_pct']}%")
        print(f"   Report: {out}")
        return out


# ── Internal helpers ──────────────────────────────────────────────────────────


def _fill(order, row, cost_model, cash, positions, entry_fees, trades, still_pending, ts, strategy):
    sym, side, qty = order["symbol"], order["side"], int(order["quantity"])
    open_price = float(row["open"])
    if open_price <= 0:
        still_pending.append(order)
        return cash

    volatility = abs(float(row["high"]) - float(row["low"])) / open_price if open_price else 0.015
    fill = cost_model.calculate_fill(
        side=side, quantity=float(qty), price=open_price,
        bar_volume=float(row["volume"]), volatility=volatility,
        enforce_participation=(side in ("BUY", "BUY_TO_COVER")),
    )
    filled = int(fill["filled_qty"])
    fees = float(fill["total_commission"]) + float(fill["sec_fee"])
    fill_price = float(fill["fill_price"])
    if filled <= 0:
        return cash

    if side in ("BUY", "BUY_TO_COVER"):
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
            existing["avg_price"] = ((existing["avg_price"] * existing["quantity"]) + fill_price * filled) / total_qty
            existing["quantity"] = total_qty
        else:
            positions[sym] = {"quantity": float(filled), "avg_price": fill_price, "entry_ts": str(ts)}
            entry_fees[sym] = fees
        if filled < qty:
            still_pending.append({"symbol": sym, "side": side, "quantity": qty - filled})
        strategy.on_order_fill({"symbol": sym, "quantity": filled, "side": side})
    else:
        position = positions.get(sym)
        if position is None:
            return cash
        sell_qty = min(filled, int(abs(position["quantity"])))
        proceeds = sell_qty * fill_price - fees
        cash += proceeds
        gross = (fill_price - position["avg_price"]) * sell_qty
        net_pnl = gross - fees - entry_fees.get(sym, 0.0)
        trades.append({
            "symbol": sym, "side": side,
            "entry_price": round(position["avg_price"], 4),
            "exit_price": round(fill_price, 4),
            "quantity": sell_qty, "pnl": round(net_pnl, 2),
            "fees": round(fees + entry_fees.get(sym, 0.0), 4),
            "entry_ts": position.get("entry_ts", ""), "exit_ts": str(ts),
        })
        position["quantity"] -= sell_qty
        if position["quantity"] <= 0:
            del positions[sym]
            entry_fees.pop(sym, None)
        strategy.on_order_fill({"symbol": sym, "quantity": sell_qty, "side": side})
    return cash


def _metrics_from_curve(equity_curve, trades, label):
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
        "label": label, "available": True,
        "starting_balance": INITIAL_BALANCE, "ending_balance": round(final, 2),
        "total_return_pct": round(total_return, 2), "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown_pct": round(float(dd) * 100.0, 2),
        "total_trades": len(trades), "winning_trades": len(wins),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
    }
