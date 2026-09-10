"""Precious metals momentum breakout strategy (long + short).

Exploits explosive breakouts in metals prices, typically driven by macro
regime shifts (inflation fears, supply shocks, geopolitical events).

Rules:
  Entry (BUY):
    - close > highest_close(lookback) + ATR  upside breakout
    - volume > avg_volume × 1.5              participation confirmed
    - close > SMA(sma_trend)                 aligned with trend
  Entry (SELL_SHORT):
    - close < lowest_close(lookback) - ATR   downside breakdown
    - volume > avg_volume × 1.5              selling pressure
    - close < SMA(sma_trend)                 aligned with trend
  Exit:
    - Trailing stop (ATR-based)
    - Time stop
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from pyrobot.indicators import Indicators
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.stock_frame import StockFrame
from pyrobot.strategies.base import MultiSymbolStrategy, StrategyState

logger = get_logger("metals_momentum")


class MetalsMomentumBreakout(MultiSymbolStrategy):
    """Momentum breakout strategy for precious metals — long and short."""

    DEFAULT_PARAMETERS = {
        "lookback": 20,
        "atr_period": 14,
        "sma_trend": 100,
        "volume_mult": 1.5,
        "trailing_stop_atr_mult": 2.0,
        "max_holding_days": 25,
        "min_history_bars": 120,
    }

    def __init__(self, strategy_id: str, symbols: list[str], parameters: Optional[Dict[str, Any]] = None) -> None:
        merged = dict(self.DEFAULT_PARAMETERS)
        if parameters:
            merged.update(parameters)
        super().__init__(strategy_id, symbols, merged)
        self._min_history_bars: int = int(self._parameters["min_history_bars"])
        self._holding: Dict[str, bool] = {s: False for s in self._symbols}
        self._holding_direction: Dict[str, str] = {s: "flat" for s in self._symbols}
        self._entry_bar_idx: Dict[str, int] = {s: 0 for s in self._symbols}
        self._entry_price: Dict[str, float] = {}
        self._bar_count: int = 0

    def initialize(self) -> None:
        self._set_state(StrategyState.INITIALIZED)
        logger.info(
            "MetalsMomentumBreakout %s initialized: lookback=%d atr_mult=%.1f",
            self._strategy_id, self._parameters["lookback"], self._parameters["trailing_stop_atr_mult"],
        )

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        try:
            self._bar_count += 1
            return self._evaluate(symbol, stock_frame)
        except Exception as exc:
            logger.error("MetalsMomentumBreakout.evaluate failed for %s: %s", symbol, exc)
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
            self._entry_price.pop(symbol, None)
            self.set_symbol_state(symbol, "holding", False)
        elif direction in ("BUY", "BUY_TO_COVER"):
            self._holding[symbol] = True
            self._entry_bar_idx[symbol] = self._bar_count
            self.set_symbol_state(symbol, "holding", True)
        else:
            if self._holding.get(symbol, False):
                self._holding[symbol] = False
                self._holding_direction[symbol] = "flat"
                self._entry_price.pop(symbol, None)
                self.set_symbol_state(symbol, "holding", False)
            else:
                self._holding[symbol] = True
                self._entry_bar_idx[symbol] = self._bar_count
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
        indicator_client.average_true_range(period=int(self._parameters["atr_period"]))

        symbol_rows = frame.xs(symbol, level="symbol")
        if len(symbol_rows) < self._min_history_bars:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Warm-up: {len(symbol_rows)} bars < {self._min_history_bars}",
            )

        close = float(symbol_rows["close"].iloc[-1])
        sma = _safe_value(symbol_rows["sma_trend"].iloc[-1])
        atr = _safe_value(symbol_rows["average_true_range"].iloc[-1])

        if sma is None or atr is None:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id, reason="Indicators unavailable",
            )

        sma, atr = float(sma), float(atr)
        lookback = int(self._parameters["lookback"])
        closes = symbol_rows["close"].astype(float)
        high_close = float(closes.iloc[-(lookback + 1):-1].max()) if len(closes) > lookback else float(closes.iloc[-lookback:].max())
        low_close = float(closes.iloc[-(lookback + 1):-1].min()) if len(closes) > lookback else float(closes.iloc[-lookback:].min())

        volumes = symbol_rows["volume"].astype(float)
        avg_vol = float(volumes.rolling(20).mean().iloc[-1]) if len(volumes) >= 20 else float(volumes.mean())
        current_vol = float(volumes.iloc[-1])
        volume_ok = current_vol > avg_vol * float(self._parameters["volume_mult"])

        holding = self._holding.get(symbol, False)
        trail_mult = float(self._parameters["trailing_stop_atr_mult"])

        # Exit
        if holding:
            entry_bar = self._entry_bar_idx.get(symbol, 0)
            bars_held = self._bar_count - entry_bar
            if bars_held > int(self._parameters["max_holding_days"]):
                action = SignalAction.SELL if self._holding_direction.get(symbol) == "long" else SignalAction.BUY_TO_COVER
                return self._make_signal(symbol, action, 0.9, f"Time stop: held {bars_held} bars")

            entry_p = self._entry_price.get(symbol, close)
            if self._holding_direction.get(symbol) == "long":
                stop_level = entry_p - trail_mult * atr
                if close < stop_level:
                    return self._make_signal(symbol, SignalAction.SELL, 0.85,
                        f"ATR trailing stop: close {close:.2f} < {stop_level:.2f}")
            else:
                stop_level = entry_p + trail_mult * atr
                if close > stop_level:
                    return self._make_signal(symbol, SignalAction.BUY_TO_COVER, 0.85,
                        f"ATR trailing stop: close {close:.2f} > {stop_level:.2f}")

            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Holding: bars_held={bars_held}, close={close:.2f}",
            )

        # Long entry
        if close > high_close + atr and close > sma and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.BUY, confidence=0.6,
                strategy_id=self._strategy_id,
                reason=f"Metals upside breakout: close {close:.2f} > {high_close:.2f}+ATR {atr:.2f}, "
                       f"SMA {sma:.2f}, vol spike",
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "long"
            self._entry_price[symbol] = close
            return signal

        # Short entry
        if close < low_close - atr and close < sma and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.SELL_SHORT, confidence=0.6,
                strategy_id=self._strategy_id,
                reason=f"Metals downside breakout: close {close:.2f} < {low_close:.2f}-ATR {atr:.2f}, "
                       f"SMA {sma:.2f}, vol spike",
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "short"
            self._entry_price[symbol] = close
            return signal

        return Signal(
            symbol=symbol, action=SignalAction.HOLD,
            strategy_id=self._strategy_id,
            reason=f"No breakout: close={close:.2f} high({lookback})={high_close:.2f} "
                   f"low({lookback})={low_close:.2f} atr={atr:.2f}",
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
