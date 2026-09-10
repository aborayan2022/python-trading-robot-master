"""Precious metals trend-following strategy (long + short).

Rules (all confirmed on the bar's close):
  Entry (BUY), only when flat:
    - close > SMA(50)                        medium-term uptrend
    - EMA(10) > EMA(30)                      short-term momentum
    - RSI(14) in [40, 70]                    not overheated
  Entry (SELL_SHORT), only when flat:
    - close < SMA(50)                        medium-term downtrend
    - EMA(10) < EMA(30)                      short-term weakness
    - RSI(14) in [30, 60]                    not oversold
  Exit:
    - close < EMA(30) (long) / close > EMA(30) (short)  trend break
    - RSI extreme (>= 75 for long, <= 25 for short)       overbought/oversold
    - trailing stop (8%)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from pyrobot.indicators import Indicators
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.stock_frame import StockFrame
from pyrobot.strategies.base import MultiSymbolStrategy, StrategyState

logger = get_logger("metals_trend")


class MetalsTrendFollowStrategy(MultiSymbolStrategy):
    """Trend-following strategy for precious metals — long and short."""

    DEFAULT_PARAMETERS = {
        "sma_trend": 50,
        "ema_fast": 10,
        "ema_slow": 30,
        "rsi_period": 14,
        "rsi_long_min": 40.0,
        "rsi_long_max": 70.0,
        "rsi_short_min": 30.0,
        "rsi_short_max": 60.0,
        "rsi_exit_long": 75.0,
        "rsi_exit_short": 25.0,
        "trailing_stop_pct": 0.08,
        "min_history_bars": 60,
    }

    def __init__(self, strategy_id: str, symbols: list[str], parameters: Optional[Dict[str, Any]] = None) -> None:
        merged = dict(self.DEFAULT_PARAMETERS)
        if parameters:
            merged.update(parameters)
        super().__init__(strategy_id, symbols, merged)
        self._min_history_bars: int = int(self._parameters["min_history_bars"])
        self._holding: Dict[str, bool] = {s: False for s in self._symbols}
        self._holding_direction: Dict[str, str] = {s: "flat" for s in self._symbols}
        self._entry_high: Dict[str, float] = {}
        self._entry_low: Dict[str, float] = {}

    def initialize(self) -> None:
        self._set_state(StrategyState.INITIALIZED)
        logger.info(
            "MetalsTrendFollowStrategy %s initialized: sma=%d ema=%d/%d rsi=%d",
            self._strategy_id,
            self._parameters["sma_trend"],
            self._parameters["ema_fast"],
            self._parameters["ema_slow"],
            self._parameters["rsi_period"],
        )

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        try:
            return self._evaluate(symbol, stock_frame)
        except Exception as exc:
            logger.error("MetalsTrendFollowStrategy.evaluate failed for %s: %s", symbol, exc)
            return Signal(
                symbol=symbol, action=SignalAction.NO_TRADE,
                strategy_id=self._strategy_id, reason=f"Evaluation error: {exc}",
            )

    def on_order_fill(self, order_dict: dict) -> None:
        symbol = order_dict.get("symbol")
        if not symbol:
            return
        raw_qty = order_dict.get("filled_quantity", order_dict.get("quantity", 0))
        try:
            filled_qty = float(raw_qty or 0.0)
        except (TypeError, ValueError):
            filled_qty = 0.0
        if filled_qty <= 0:
            return

        direction = str(order_dict.get("instruction", order_dict.get("side", ""))).upper()
        if direction in ("SELL", "SELL_SHORT"):
            self._holding[symbol] = False
            self._holding_direction[symbol] = "flat"
            self._entry_high.pop(symbol, None)
            self._entry_low.pop(symbol, None)
            self.set_symbol_state(symbol, "holding", False)
        elif direction in ("BUY", "BUY_TO_COVER"):
            self._holding[symbol] = True
            self._entry_high.setdefault(symbol, 0.0)
            self._entry_low.setdefault(symbol, float("inf"))
            self.set_symbol_state(symbol, "holding", True)
        else:
            if self._holding.get(symbol, False):
                self._holding[symbol] = False
                self._holding_direction[symbol] = "flat"
                self._entry_high.pop(symbol, None)
                self._entry_low.pop(symbol, None)
                self.set_symbol_state(symbol, "holding", False)
            else:
                self._holding[symbol] = True
                self._entry_high.setdefault(symbol, 0.0)
                self._entry_low.setdefault(symbol, float("inf"))
                self.set_symbol_state(symbol, "holding", True)

    def get_holding(self, symbol: str) -> bool:
        return bool(self._holding.get(symbol, False))

    def _evaluate(self, symbol: str, stock_frame: StockFrame) -> Signal:
        frame = stock_frame.frame
        has_symbol = symbol in frame.index.get_level_values(0)
        if not has_symbol:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id, reason=f"No data yet for {symbol}",
            )

        indicator_client = Indicators(price_data_frame=stock_frame)
        indicator_client.sma(period=int(self._parameters["sma_trend"]), column_name="sma_trend")
        indicator_client.ema(period=int(self._parameters["ema_fast"]), column_name="ema_fast")
        indicator_client.ema(period=int(self._parameters["ema_slow"]), column_name="ema_slow")
        indicator_client.rsi(period=int(self._parameters["rsi_period"]))

        symbol_rows = frame.xs(symbol, level="symbol")
        if len(symbol_rows) < self._min_history_bars:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Warm-up: {len(symbol_rows)} bars < {self._min_history_bars}",
            )

        close = float(symbol_rows["close"].iloc[-1])
        sma = _safe_value(symbol_rows["sma_trend"].iloc[-1])
        ema_f = _safe_value(symbol_rows["ema_fast"].iloc[-1])
        ema_s = _safe_value(symbol_rows["ema_slow"].iloc[-1])
        rsi = _safe_value(symbol_rows["rsi"].iloc[-1])

        if sma is None or ema_f is None or ema_s is None or rsi is None:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id, reason="Indicators unavailable",
            )

        sma, ema_f, ema_s, rsi = float(sma), float(ema_f), float(ema_s), float(rsi)
        holding = self._holding.get(symbol, False)
        trailing_pct = float(self._parameters["trailing_stop_pct"])

        if holding:
            direction = self._holding_direction.get(symbol, "flat")
            if direction == "long":
                self._entry_high[symbol] = max(self._entry_high.get(symbol, 0.0), close)
                if close < ema_s or rsi >= float(self._parameters["rsi_exit_long"]):
                    return self._make_signal(symbol, SignalAction.SELL, 0.8,
                        f"Long exit: close {close:.2f} < EMA {ema_s:.2f} or RSI {rsi:.1f} >= {self._parameters['rsi_exit_long']}")
                if close < self._entry_high.get(symbol, 0.0) * (1.0 - trailing_pct):
                    return self._make_signal(symbol, SignalAction.SELL, 0.8,
                        f"Trailing stop: close {close:.2f} < high × (1-{trailing_pct})")
            else:
                self._entry_low[symbol] = min(self._entry_low.get(symbol, float("inf")), close)
                if close > ema_s or rsi <= float(self._parameters["rsi_exit_short"]):
                    return self._make_signal(symbol, SignalAction.BUY_TO_COVER, 0.8,
                        f"Short exit: close {close:.2f} > EMA {ema_s:.2f} or RSI {rsi:.1f} <= {self._parameters['rsi_exit_short']}")
                if close > self._entry_low.get(symbol, 0.0) * (1.0 + trailing_pct):
                    return self._make_signal(symbol, SignalAction.BUY_TO_COVER, 0.8,
                        f"Trailing stop: close {close:.2f} > low × (1+{trailing_pct})")
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Holding {direction}: close={close:.2f} ema_s={ema_s:.2f} rsi={rsi:.1f}",
            )

        # Long entry
        if (close > sma > 0 and ema_f > ema_s
                and float(self._parameters["rsi_long_min"]) <= rsi <= float(self._parameters["rsi_long_max"])):
            signal = Signal(
                symbol=symbol, action=SignalAction.BUY, confidence=0.62,
                strategy_id=self._strategy_id,
                reason=f"Metals uptrend: close {close:.2f} > SMA {sma:.2f}, EMA{int(self._parameters['ema_fast'])} > "
                       f"EMA{int(self._parameters['ema_slow'])}, RSI {rsi:.1f}",
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "long"
            return signal

        # Short entry
        if (close < sma and sma > 0 and ema_f < ema_s
                and float(self._parameters["rsi_short_min"]) <= rsi <= float(self._parameters["rsi_short_max"])):
            signal = Signal(
                symbol=symbol, action=SignalAction.SELL_SHORT, confidence=0.62,
                strategy_id=self._strategy_id,
                reason=f"Metals downtrend: close {close:.2f} < SMA {sma:.2f}, EMA{int(self._parameters['ema_fast'])} < "
                       f"EMA{int(self._parameters['ema_slow'])}, RSI {rsi:.1f}",
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "short"
            return signal

        return Signal(
            symbol=symbol, action=SignalAction.HOLD,
            strategy_id=self._strategy_id,
            reason=f"No signal: close={close:.2f} sma={sma:.2f} ema_f={ema_f:.2f} ema_s={ema_s:.2f} rsi={rsi:.1f}",
        )

    def _make_signal(self, symbol: str, action: SignalAction, confidence: float, reason: str) -> Signal:
        signal = Signal(symbol=symbol, action=action, confidence=confidence,
                        strategy_id=self._strategy_id, reason=reason)
        self._record_signal(signal)
        self._set_state(StrategyState.RUNNING)
        return signal


def _safe_value(value) -> Optional[float]:
    if value is None:
        return None
    try:
        result = float(value)
        if np.isnan(result) or np.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None
