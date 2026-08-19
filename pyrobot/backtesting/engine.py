"""Backtesting engine for simulating strategies against historical data."""

import numpy as np
import pandas as pd

from datetime import datetime
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.stock_frame import StockFrame
from pyrobot.logging_config import get_logger

logger = get_logger("backtesting")


class BacktestResult:
    """Container for backtesting results."""

    def __init__(self) -> None:
        self.trades: List[dict] = []
        self.equity_curve: List[float] = []
        self.daily_returns: List[float] = []
        self.starting_balance: float = 0.0
        self.ending_balance: float = 0.0

    @property
    def total_return(self) -> float:
        if self.starting_balance == 0:
            return 0.0
        return (self.ending_balance - self.starting_balance) / self.starting_balance

    @property
    def total_return_pct(self) -> float:
        return self.total_return * 100

    @property
    def sharpe_ratio(self) -> float:
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        returns = np.array(self.daily_returns)
        if returns.std() == 0:
            return 0.0
        return float(np.sqrt(252) * returns.mean() / returns.std())

    @property
    def sortino_ratio(self) -> float:
        if not self.daily_returns or len(self.daily_returns) < 2:
            return 0.0
        returns = np.array(self.daily_returns)
        downside = returns[returns < 0]
        if len(downside) == 0 or downside.std() == 0:
            return 0.0
        return float(np.sqrt(252) * returns.mean() / downside.std())

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
        return gross_profit / gross_loss

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
        engine = BacktestEngine(
            initial_balance=100_000,
            historical_data=[...],
        )

        def my_strategy(stock_frame, indicators):
            # Return 'buy', 'sell', or None
            ...

        result = engine.run(strategy=my_strategy, indicator_setup=my_setup)
    """

    def __init__(
        self,
        initial_balance: float = 100000.0,
        historical_data: List[dict] = None,
        commission_per_trade: float = 0.0,
        slippage_pct: float = 0.0,
    ) -> None:
        self.initial_balance = initial_balance
        self.historical_data = historical_data or []
        self.commission_per_trade = commission_per_trade
        self.slippage_pct = slippage_pct
        self.paper_broker = PaperBroker(initial_balance=initial_balance)

    def run(
        self,
        strategy: Callable,
        indicator_setup: Callable = None,
        bar_size: int = 1,
        bar_type: str = "minute",
        stop_loss_pct: float = None,
        take_profit_pct: float = None,
    ) -> BacktestResult:
        """Run a backtest with the given strategy.

        Arguments:
            strategy: A callable that takes (stock_frame, indicator_client)
                      and returns 'buy', 'sell', or None.
            indicator_setup: Optional callable that takes an Indicators instance
                             and configures indicators/signals.
            stop_loss_pct: Optional stop loss as a decimal (e.g. 0.05 for 5%).
            take_profit_pct: Optional take profit as a decimal.

        Returns:
            BacktestResult with all metrics.
        """
        from pyrobot.indicators import Indicators

        result = BacktestResult()
        result.starting_balance = self.initial_balance

        if not self.historical_data:
            logger.warning("No historical data provided for backtest")
            return result

        stock_frame = StockFrame(data=self.historical_data)

        indicator_client = Indicators(price_data_frame=stock_frame)
        if indicator_setup:
            indicator_setup(indicator_client)

        symbols = stock_frame.frame.index.get_level_values(0).unique().tolist()

        for symbol in symbols:
            self.paper_broker.update_prices(
                {symbol: {"close": 0.0, "last_price": 0.0}}
            )

        position_entries: Dict[str, float] = {}

        symbol_groups = stock_frame.frame.groupby(level=0)
        timestamps = stock_frame.frame.index.get_level_values(1).unique().sort_values()

        for ts in timestamps:
            for symbol in symbols:
                try:
                    row = stock_frame.frame.loc[(symbol, ts)]
                except KeyError:
                    continue

                current_price = row.get("close", 0.0)
                if current_price <= 0:
                    continue

                self.paper_broker.update_prices(
                    {symbol: {"close": current_price, "last_price": current_price}}
                )

            indicator_client.refresh()
            signal = strategy(stock_frame, indicator_client)

            if signal == "buy":
                for symbol in symbols:
                    if symbol not in position_entries:
                        try:
                            current_row = stock_frame.frame.loc[(symbol, ts)]
                            price = current_row.get("close", 0.0)
                            if price > 0:
                                fill_price = price * (1 + self.slippage_pct)
                                quantity = int(
                                    (self.paper_broker._cash_balance * 0.95)
                                    / fill_price
                                )
                                if quantity > 0:
                                    order = {
                                        "orderType": "MARKET",
                                        "orderLegCollection": [
                                            {
                                                "instruction": "BUY",
                                                "quantity": quantity,
                                                "instrument": {
                                                    "symbol": symbol,
                                                    "assetType": "EQUITY",
                                                },
                                            }
                                        ],
                                    }
                                    response = self.paper_broker.place_order(
                                        account="BACKTEST", order=order
                                    )
                                    if response["status"] == "FILLED":
                                        position_entries[symbol] = fill_price
                                        self.paper_broker._cash_balance -= (
                                            self.commission_per_trade
                                        )
                        except (KeyError, TypeError):
                            pass

            elif signal == "sell":
                for symbol in list(position_entries.keys()):
                    try:
                        current_row = stock_frame.frame.loc[(symbol, ts)]
                        price = current_row.get("close", 0.0)
                        if price > 0:
                            fill_price = price * (1 - self.slippage_pct)
                            quantity = 0
                            for pos in self.paper_broker._positions.values():
                                if pos["symbol"] == symbol:
                                    quantity = pos["quantity"]
                                    break

                            if quantity > 0:
                                entry_price = position_entries[symbol]
                                pnl = (fill_price - entry_price) * quantity
                                order = {
                                    "orderType": "MARKET",
                                    "orderLegCollection": [
                                        {
                                            "instruction": "SELL",
                                            "quantity": quantity,
                                            "instrument": {
                                                "symbol": symbol,
                                                "assetType": "EQUITY",
                                            },
                                        }
                                    ],
                                }
                                response = self.paper_broker.place_order(
                                    account="BACKTEST", order=order
                                )
                                if response["status"] == "FILLED":
                                    result.trades.append(
                                        {
                                            "symbol": symbol,
                                            "entry_price": entry_price,
                                            "exit_price": fill_price,
                                            "quantity": quantity,
                                            "pnl": pnl,
                                            "timestamp": str(ts),
                                        }
                                    )
                                    self.paper_broker._cash_balance -= (
                                        self.commission_per_trade
                                    )
                                    del position_entries[symbol]
                    except (KeyError, TypeError):
                        pass

            if stop_loss_pct or take_profit_pct:
                for symbol in list(position_entries.keys()):
                    try:
                        current_row = stock_frame.frame.loc[(symbol, ts)]
                        price = current_row.get("close", 0.0)
                        entry_price = position_entries[symbol]

                        if stop_loss_pct and price <= entry_price * (1 - stop_loss_pct):
                            quantity = 0
                            for pos in self.paper_broker._positions.values():
                                if pos["symbol"] == symbol:
                                    quantity = pos["quantity"]
                                    break
                            if quantity > 0:
                                pnl = (price - entry_price) * quantity
                                order = {
                                    "orderType": "MARKET",
                                    "orderLegCollection": [
                                        {
                                            "instruction": "SELL",
                                            "quantity": quantity,
                                            "instrument": {
                                                "symbol": symbol,
                                                "assetType": "EQUITY",
                                            },
                                        }
                                    ],
                                }
                                self.paper_broker.place_order(
                                    account="BACKTEST", order=order
                                )
                                result.trades.append(
                                    {
                                        "symbol": symbol,
                                        "entry_price": entry_price,
                                        "exit_price": price,
                                        "quantity": quantity,
                                        "pnl": pnl,
                                        "timestamp": str(ts),
                                        "exit_reason": "stop_loss",
                                    }
                                )
                                del position_entries[symbol]

                        elif take_profit_pct and price >= entry_price * (1 + take_profit_pct):
                            quantity = 0
                            for pos in self.paper_broker._positions.values():
                                if pos["symbol"] == symbol:
                                    quantity = pos["quantity"]
                                    break
                            if quantity > 0:
                                pnl = (price - entry_price) * quantity
                                order = {
                                    "orderType": "MARKET",
                                    "orderLegCollection": [
                                        {
                                            "instruction": "SELL",
                                            "quantity": quantity,
                                            "instrument": {
                                                "symbol": symbol,
                                                "assetType": "EQUITY",
                                            },
                                        }
                                    ],
                                }
                                self.paper_broker.place_order(
                                    account="BACKTEST", order=order
                                )
                                result.trades.append(
                                    {
                                        "symbol": symbol,
                                        "entry_price": entry_price,
                                        "exit_price": price,
                                        "quantity": quantity,
                                        "pnl": pnl,
                                        "timestamp": str(ts),
                                        "exit_reason": "take_profit",
                                    }
                                )
                                del position_entries[symbol]
                    except (KeyError, TypeError):
                        pass

            account_info = self.paper_broker.get_account_info()
            total_value = (
                account_info["cash_balance"] + account_info["long_market_value"]
            )
            result.equity_curve.append(total_value)

            if len(result.equity_curve) >= 2:
                daily_ret = (
                    result.equity_curve[-1] - result.equity_curve[-2]
                ) / result.equity_curve[-2]
                result.daily_returns.append(daily_ret)

        result.ending_balance = result.equity_curve[-1] if result.equity_curve else self.initial_balance

        logger.info(f"Backtest complete: {result}")
        return result
