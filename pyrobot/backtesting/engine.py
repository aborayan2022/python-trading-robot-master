"""Backtesting engine for simulating strategies against historical data.

Honesty contract (enforced by tests):
- Signals generated from bar t data are filled at bar t+1 OPEN, never the same bar.
- Strategies only receive rows up to the current bar (no lookahead).
- Fills pass through ExecutionCostModel: spread, volatility-adjusted slippage,
  square-root market impact, volume-participation partial fills, commissions, SEC fees.
- Stop-loss / take-profit exits are evaluated intrabar against OHLC with gap handling;
  when both barriers are touched in one bar the stop is assumed to hit first (conservative).
"""

from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from pyrobot.backtesting.cost_model import CostModelConfig, ExecutionCostModel
from pyrobot.backtesting.metrics import calculate_quantitative_metrics
from pyrobot.logging_config import get_logger
from pyrobot.stock_frame import StockFrame

logger = get_logger("backtesting")

# Annualization factors per bar type.
_PERIODS_PER_YEAR: Dict[str, float] = {
    "minute": 252 * 390,
    "hour": 252 * 6.5,
    "hourly": 252 * 6.5,
    "day": 252,
    "daily": 252,
    "week": 52,
    "weekly": 52,
}


def _num(row: "pd.Series", key: str, default: float) -> float:
    """Read a numeric cell, falling back when the column is missing or NaN."""
    val = row.get(key, default)
    if val is None or pd.isna(val):
        return default
    return float(val)


class _Position:
    """Internal open position tracked by the engine."""

    __slots__ = ("symbol", "quantity", "avg_price", "entry_fees", "entry_bar")

    def __init__(self, symbol: str, quantity: float, avg_price: float, fees: float, entry_bar: int) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self.avg_price = avg_price
        self.entry_fees = fees
        self.entry_bar = entry_bar


class BacktestResult:
    """Container for backtesting results.

    Ratio metrics (Sharpe/Sortino) delegate to
    pyrobot.backtesting.metrics.calculate_quantitative_metrics and are annualized
    using periods_per_year (derived from the bar type) instead of a hardcoded 252.
    """

    def __init__(self, periods_per_year: int = 252) -> None:
        self.trades: List[dict] = []
        self.equity_curve: List[float] = []
        self.daily_returns: List[float] = []
        self.starting_balance: float = 0.0
        self.ending_balance: float = 0.0
        self.periods_per_year: int = periods_per_year

    @property
    def total_return(self) -> float:
        if self.starting_balance == 0:
            return 0.0
        return (self.ending_balance - self.starting_balance) / self.starting_balance

    @property
    def total_return_pct(self) -> float:
        return self.total_return * 100

    def _report(self):
        """Quantitative report; synthesizes an equity curve from returns if absent."""
        equity = self.equity_curve
        if not equity and self.daily_returns:
            equity = list(100000.0 * np.cumprod([1.0 + r for r in self.daily_returns]))
        return calculate_quantitative_metrics(
            self.daily_returns, equity, self.trades,
            periods_per_year=self.periods_per_year,
        )

    @property
    def sharpe_ratio(self) -> float:
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        return float(self._report().sharpe_ratio)

    @property
    def sortino_ratio(self) -> float:
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        return float(self._report().sortino_ratio)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0
        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        return float(drawdown.min())

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.get("pnl", 0) > 0)
        return wins / len(self.trades)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.get("pnl", 0) for t in self.trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t.get("pnl", 0) for t in self.trades if t.get("pnl", 0) < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return float(gross_profit / gross_loss)

    def summary(self) -> dict:
        return {
            "starting_balance": self.starting_balance,
            "ending_balance": self.ending_balance,
            "total_return_pct": round(self.total_return_pct, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "sortino_ratio": round(self.sortino_ratio, 4),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "win_rate_pct": round(self.win_rate * 100, 2),
            "total_trades": self.total_trades,
            "profit_factor": round(self.profit_factor, 4) if self.profit_factor != float("inf") else "inf",
        }

    def __repr__(self) -> str:
        s = self.summary()
        return (
            f"BacktestResult(return={s['total_return_pct']}%, "
            f"sharpe={s['sharpe_ratio']}, max_dd={s['max_drawdown_pct']}%, "
            f"trades={s['total_trades']}, win_rate={s['win_rate_pct']}%)"
        )


class BacktestEngine:
    """Engine for running backtests against historical data.

    Usage:
        engine = BacktestEngine(initial_balance=100_000, historical_data=[...])
        result = engine.run(strategy=my_strategy)

    The strategy callable receives (stock_frame, indicator_client) where the frame
    contains ONLY rows up to and including the current bar, and returns 'buy',
    'sell', or None. Orders generated on bar t are filled at bar t+1's open.
    """

    def __init__(
        self,
        initial_balance: float = 100000.0,
        historical_data: Optional[List[dict]] = None,
        commission_per_trade: float = 0.0,
        slippage_pct: float = 0.0,
        position_size_fraction: float = 0.95,
        cost_model: Optional[ExecutionCostModel] = None,
    ) -> None:
        self.initial_balance = initial_balance
        self.historical_data = historical_data or []
        self.commission_per_trade = commission_per_trade
        self.slippage_pct = slippage_pct
        self.position_size_fraction = position_size_fraction
        self.cost_model = cost_model or self._build_cost_model()

    def _build_cost_model(self) -> ExecutionCostModel:
        """Derive a cost model from the legacy constructor parameters.

        Legacy params map conservatively: flat per-trade commission becomes the
        min commission with zero per-share fees; slippage_pct becomes base
        slippage in bps. Market impact and volume participation keep their
        defaults so partial fills / impact are always modeled.
        """
        cfg = CostModelConfig()
        if self.commission_per_trade > 0:
            cfg.commission_per_share = 0.0
            cfg.min_commission = self.commission_per_trade
        else:
            cfg.commission_per_share = 0.0
            cfg.min_commission = 0.0
        cfg.base_slippage_bps = self.slippage_pct * 10000.0 if self.slippage_pct > 0 else 0.0
        cfg.half_spread_bps = 0.0
        return ExecutionCostModel(config=cfg)

    def run(
        self,
        strategy: Callable,
        indicator_setup: Optional[Callable] = None,
        bar_size: int = 1,
        bar_type: str = "minute",
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
    ) -> BacktestResult:
        """Run a backtest with the given strategy.

        Arguments:
            strategy: A callable that takes (stock_frame, indicator_client)
                      and returns 'buy', 'sell', or None.
            indicator_setup: Optional callable that takes an Indicators instance
                             and configures indicators/signals.
            bar_size: Bar size multiplier (informational; used with bar_type).
            bar_type: One of 'minute', 'hour', 'day' — drives return annualization.
            stop_loss_pct: Optional stop loss as a decimal (e.g. 0.05 for 5%).
            take_profit_pct: Optional take profit as a decimal.

        Returns:
            BacktestResult with all metrics.
        """
        from pyrobot.indicators import Indicators

        periods_per_year = int(_PERIODS_PER_YEAR.get(bar_type.lower(), 252))
        result = BacktestResult(periods_per_year=periods_per_year)
        result.starting_balance = self.initial_balance

        if not self.historical_data:
            logger.warning("No historical data provided for backtest")
            return result

        full_frame = StockFrame(data=self.historical_data).frame.sort_index()
        symbols = full_frame.index.get_level_values(0).unique().tolist()
        timestamps = full_frame.index.get_level_values(1).unique().sort_values()

        cash = float(self.initial_balance)
        positions: Dict[str, _Position] = {}
        # Pending market orders produced by the previous bar's signal, filled at
        # the current bar's open. A partial fill re-queues the remainder.
        pending_orders: List[dict] = []

        indicator_client = Indicators(price_data_frame=StockFrame(data=self.historical_data))
        if indicator_setup:
            indicator_setup(indicator_client)

        # Rows accumulated so far; the strategy's view is rebuilt from these so it
        # can never observe future bars. Growing incrementally keeps per-step cost
        # proportional to the new rows only.
        visible_rows: List[dict] = []
        row_lookup: Dict[tuple, dict] = {}

        for bar_index, ts in enumerate(timestamps):
            for symbol in symbols:
                try:
                    row = full_frame.loc[(symbol, ts)]
                except KeyError:
                    continue
                close = _num(row, "close", 0.0)
                row_dict = {
                    "symbol": symbol,
                    "open": _num(row, "open", close),
                    "high": _num(row, "high", max(close, _num(row, "open", close))),
                    "low": _num(row, "low", min(close, _num(row, "open", close))),
                    "close": close,
                    "volume": _num(row, "volume", 100000.0),
                    "datetime": ts,
                }
                visible_rows.append(row_dict)
                row_lookup[(symbol, ts)] = row_dict

            # 1. Fill pending orders from the previous bar at THIS bar's open.
            still_pending: List[dict] = []
            for order in pending_orders:
                row = row_lookup.get((order["symbol"], ts))
                if row is None:
                    still_pending.append(order)  # symbol has no bar this timestamp
                    continue
                cash = self._fill_order(order, row, cash, positions, result, bar_index, still_pending)
            pending_orders = still_pending

            # 2. Intrabar exit checks against OHLC (after entries at this bar's open).
            if stop_loss_pct or take_profit_pct:
                for symbol in list(positions.keys()):
                    row = row_lookup.get((symbol, ts))
                    if row is None:
                        continue
                    cash = self._check_exit(
                        positions[symbol], row, cash, positions, result,
                        stop_loss_pct, take_profit_pct, bar_index,
                    )

            # 3. Mark-to-market equity point.
            equity = cash + sum(
                p.quantity * row_lookup.get((p.symbol, ts), {}).get("close", p.avg_price)
                for p in positions.values()
            )
            result.equity_curve.append(float(equity))
            if len(result.equity_curve) >= 2:
                prev = result.equity_curve[-2]
                result.daily_returns.append((equity - prev) / prev if prev != 0 else 0.0)

            # 4. Strategy sees ONLY data up to this bar, decides for the NEXT bar.
            view_frame = self._make_view_frame(visible_rows)
            indicator_client.price_data_frame = view_frame
            signal = strategy(view_frame, indicator_client)

            if signal == "buy":
                for symbol in symbols:
                    if symbol not in positions:
                        pending_orders.append({"symbol": symbol, "side": "BUY", "quantity": None})
            elif signal == "sell":
                for symbol in list(positions.keys()):
                    pending_orders.append({
                        "symbol": symbol, "side": "SELL", "quantity": positions[symbol].quantity,
                    })

        result.ending_balance = (
            result.equity_curve[-1] if result.equity_curve else self.initial_balance
        )
        logger.info(f"Backtest complete: {result}")
        return result

    def _make_view_frame(self, visible_rows: List[dict]) -> StockFrame:
        """Wrap accumulated past rows in a StockFrame without future data."""
        frame = StockFrame.__new__(StockFrame)
        frame._data = visible_rows
        frame._frame = pd.DataFrame(data=visible_rows).set_index(["symbol", "datetime"]) if visible_rows else pd.DataFrame()
        frame._symbol_groups = None
        frame._symbol_rolling_groups = None
        return frame

    def _fill_order(
        self,
        order: dict,
        row: dict,
        cash: float,
        positions: Dict[str, _Position],
        result: BacktestResult,
        bar_index: int,
        still_pending: List[dict],
    ) -> float:
        """Fill a market order at the bar's open through the cost model."""
        symbol, side = order["symbol"], order["side"]
        open_price = row["open"]
        if open_price <= 0:
            still_pending.append(order)
            return cash

        if order.get("quantity") is None:
            equity = cash + sum(p.quantity * p.avg_price for p in positions.values())
            budget = equity * self.position_size_fraction
            qty = int(budget / open_price)
            if qty <= 0:
                return cash
        else:
            qty = int(order["quantity"])

        bar_volatility = self._bar_volatility(row)
        fill = self.cost_model.calculate_fill(
            side=side,
            quantity=float(qty),
            price=open_price,
            bar_volume=row.get("volume", 100000.0),
            volatility=bar_volatility,
            # Exits are liquidations: complete regardless of bar volume; the
            # sqrt-impact term prices the crowding instead of capping the fill.
            enforce_participation=(side == "BUY"),
        )
        filled = int(fill["filled_qty"])
        fees = fill["total_commission"] + fill["sec_fee"]
        fill_price = fill["fill_price"]

        if filled <= 0:
            return cash

        if side == "BUY":
            cost = filled * fill_price + fees
            if cost > cash:
                # Afford only what cash allows (recompute once, no fees-splitting complexity).
                filled = int((cash / (fill_price * (1 + 1e-9))))
                if filled <= 0:
                    return cash
                cost = filled * fill_price + fees
            cash -= cost
            existing = positions.get(symbol)
            if existing:
                total_qty = existing.quantity + filled
                existing.avg_price = (
                    (existing.avg_price * existing.quantity) + fill_price * filled
                ) / total_qty
                existing.quantity = total_qty
                existing.entry_fees += fees
            else:
                positions[symbol] = _Position(symbol, filled, fill_price, fees, bar_index)
        else:  # SELL — full exit of the position
            position = positions.get(symbol)
            if position is None:
                return cash
            sell_qty = min(filled, position.quantity)
            proceeds = sell_qty * fill_price - fees
            cash += proceeds
            gross = (fill_price - position.avg_price) * sell_qty
            net_pnl = gross - fees - position.entry_fees
            result.trades.append({
                "symbol": symbol,
                "entry_price": position.avg_price,
                "exit_price": fill_price,
                "quantity": sell_qty,
                "pnl": net_pnl,
                "entry_fees": position.entry_fees,
                "exit_fees": fees,
                "entry_bar": position.entry_bar,
                "exit_bar": bar_index,
                "timestamp": str(row.get("datetime", "")),
            })
            del positions[symbol]

        # Partial fill: re-queue the unfilled remainder for the next bar.
        if filled < qty and side == "BUY":
            remainder = qty - filled
            if remainder > 0:
                still_pending.append({"symbol": symbol, "side": side, "quantity": remainder})
        return cash

    def _check_exit(
        self,
        position: _Position,
        row: dict,
        cash: float,
        positions: Dict[str, _Position],
        result: BacktestResult,
        stop_loss_pct: Optional[float],
        take_profit_pct: Optional[float],
        bar_index: int,
    ) -> float:
        """Evaluate intrabar stop/TP using OHLC with gap handling.

        A position entered at THIS bar's open exits at the barrier price itself;
        a position from an earlier bar that gaps through its barrier exits at the
        (worse) open. If both barriers are touched in one bar, the stop is assumed
        to hit first (conservative).
        """
        symbol = position.symbol
        entry = position.avg_price
        stop_price = entry * (1 - stop_loss_pct) if stop_loss_pct else None
        tp_price = entry * (1 + take_profit_pct) if take_profit_pct else None

        exit_price = None
        reason = None
        same_bar_entry = position.entry_bar == bar_index

        stop_hit = stop_price is not None and row["low"] <= stop_price
        tp_hit = tp_price is not None and row["high"] >= tp_price

        if stop_hit:  # stop checked first (conservative)
            exit_price = stop_price if same_bar_entry else min(row["open"], stop_price)
            reason = "stop_loss"
        elif tp_hit:
            exit_price = tp_price if same_bar_entry else max(row["open"], tp_price)
            reason = "take_profit"

        if exit_price is None:
            return cash

        fill = self.cost_model.calculate_fill(
            side="SELL",
            quantity=float(position.quantity),
            price=float(exit_price),
            bar_volume=row.get("volume", 100000.0),
            volatility=self._bar_volatility(row),
            enforce_participation=False,  # stop/TP exits must complete
        )
        exit_fill = fill["fill_price"]
        fees = fill["total_commission"] + fill["sec_fee"]
        cash += position.quantity * exit_fill - fees
        gross = (exit_fill - entry) * position.quantity
        result.trades.append({
            "symbol": symbol,
            "entry_price": entry,
            "exit_price": exit_fill,
            "quantity": position.quantity,
            "pnl": gross - fees - position.entry_fees,
            "entry_fees": position.entry_fees,
            "exit_fees": fees,
            "entry_bar": position.entry_bar,
            "exit_bar": bar_index,
            "timestamp": str(row.get("datetime", "")),
            "exit_reason": reason,
        })
        del positions[symbol]
        return cash

    @staticmethod
    def _bar_volatility(row: dict) -> float:
        """Cheap per-bar volatility proxy (normalized range) for the cost model."""
        open_price = row.get("open", 0.0) or 0.0
        if open_price <= 0:
            return 0.015
        return float(abs(row.get("high", open_price) - row.get("low", open_price)) / open_price)
