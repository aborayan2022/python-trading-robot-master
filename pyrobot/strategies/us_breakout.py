"""US equity breakout strategy (long + short).

Rules (all confirmed on the bar's close):
  Entry (BUY), only when flat:
    - close > highest_close(20) + ATR(14)    upside breakout
    - volume > avg_volume(20) × 1.5          volume confirmation
    - close > SMA(100)                       trend alignment
  Entry (SELL_SHORT), only when flat:
    - close < lowest_close(20) - ATR(14)     downside breakout
    - volume > avg_volume(20) × 1.5          volume confirmation
    - close < SMA(100)                       trend alignment
  Exit:
    - close < highest_since_entry × (1 - trailing_stop_pct)  trailing stop
    - bars_held > max_holding_days                         time stop
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from pyrobot.indicators import Indicators
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.stock_frame import StockFrame
from pyrobot.strategies.base import MultiSymbolStrategy, StrategyState

logger = get_logger("us_breakout")


class USBreakoutStrategy(MultiSymbolStrategy):
    """Breakout strategy for US equities — long and short."""

    DEFAULT_PARAMETERS = {
        "lookback": 20,
        "atr_period": 14,
        "sma_trend": 100,
        "volume_mult": 1.5,
        "trailing_stop_pct": 0.04,
        "max_holding_days": 30,
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
        self._highest_since_entry: Dict[str, float] = {}
        self._lowest_since_entry: Dict[str, float] = {}
        self._bar_count: Dict[str, int] = {s: 0 for s in self._symbols}

    def initialize(self) -> None:
        self._set_state(StrategyState.INITIALIZED)
        logger.info(
            "USBreakoutStrategy %s initialized: lookback=%d atr=%d sma=%d vol_mult=%.1f trail=%.1f%%",
            self._strategy_id,
            self._parameters["lookback"],
            self._parameters["atr_period"],
            self._parameters["sma_trend"],
            self._parameters["volume_mult"],
            self._parameters["trailing_stop_pct"] * 100,
        )

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        try:
            self._bar_count[symbol] += 1
            return self._evaluate(symbol, stock_frame)
        except Exception as exc:
            logger.error("USBreakoutStrategy.evaluate failed for %s: %s", symbol, exc)
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
        if direction in ("BUY", "SELL_SHORT"):
            self._holding[symbol] = True
            self._holding_direction[symbol] = "long" if direction == "BUY" else "short"
            self._entry_bar_idx[symbol] = self._bar_count[symbol]
            self.set_symbol_state(symbol, "holding", True)
        elif direction in ("SELL", "BUY_TO_COVER"):
            self._holding[symbol] = False
            self._holding_direction[symbol] = "flat"
            self._highest_since_entry.pop(symbol, None)
            self._lowest_since_entry.pop(symbol, None)
            self.set_symbol_state(symbol, "holding", False)
        else:
            if self._holding.get(symbol, False):
                self._holding[symbol] = False
                self._holding_direction[symbol] = "flat"
                self._highest_since_entry.pop(symbol, None)
                self._lowest_since_entry.pop(symbol, None)
                self.set_symbol_state(symbol, "holding", False)
            else:
                self._holding[symbol] = True
                self._entry_bar_idx[symbol] = self._bar_count[symbol]
                self.set_symbol_state(symbol, "holding", True)

    def get_holding(self, symbol: str) -> bool:
        return bool(self._holding.get(symbol, False))

    def sync_positions(self, positions: Dict[str, float]) -> None:
        """Synchronize holding/direction state with a broker position snapshot.

        Positive quantity → long, negative quantity → short, zero → flat.
        Trailing-stop floors/peaks are re-seeded from the first bar after sync.

        Args:
            positions: symbol → quantity (per the broker account).
        """
        for symbol in self._symbols:
            try:
                qty = float(positions.get(symbol, 0.0) or 0.0)
            except (TypeError, ValueError):
                qty = 0.0
            self._holding[symbol] = qty != 0.0
            self._holding_direction[symbol] = "long" if qty > 0 else ("short" if qty < 0 else "flat")
            if qty == 0:
                self._highest_since_entry.pop(symbol, None)
                self._lowest_since_entry.pop(symbol, None)
            else:
                self._entry_bar_idx[symbol] = self._bar_count.get(symbol, 0)
                if qty > 0:
                    self._highest_since_entry[symbol] = float("-inf")
                else:
                    self._lowest_since_entry[symbol] = float("inf")
            self.set_symbol_state(symbol, "holding", qty != 0.0)
            logger.info(
                "USBreakoutStrategy %s synced position for %s: qty=%s holding=%s direction=%s",
                self._strategy_id, symbol, qty, self._holding[symbol], self._holding_direction[symbol],
            )

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
        sma_trend = _safe_value(symbol_rows["sma_trend"].iloc[-1])
        atr = _safe_value(symbol_rows["average_true_range"].iloc[-1])

        if sma_trend is None or atr is None:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id, reason="Indicators unavailable",
            )

        sma_trend = float(sma_trend)
        atr = float(atr)
        lookback = int(self._parameters["lookback"])

        closes = symbol_rows["close"].astype(float)
        high_close = float(closes.iloc[-(lookback + 1):-1].max()) if len(closes) > lookback else float(closes.iloc[-lookback:].max())
        low_close = float(closes.iloc[-(lookback + 1):-1].min()) if len(closes) > lookback else float(closes.iloc[-lookback:].min())

        volumes = symbol_rows["volume"].astype(float)
        avg_vol = float(volumes.rolling(20).mean().iloc[-1]) if len(volumes) >= 20 else float(volumes.mean())
        current_vol = float(volumes.iloc[-1])
        volume_ok = current_vol > avg_vol * float(self._parameters["volume_mult"])

        holding = self._holding.get(symbol, False)
        trailing_pct = float(self._parameters["trailing_stop_pct"])

        # Exit logic
        if holding:
            direction = self._holding_direction.get(symbol, "long")
            entry_bar = self._entry_bar_idx.get(symbol, 0)
            bars_held = self._bar_count.get(symbol, 0) - entry_bar

            if bars_held > int(self._parameters["max_holding_days"]):
                action = SignalAction.SELL if direction == "long" else SignalAction.BUY_TO_COVER
                return self._make_signal(symbol, action, 0.9, f"Time stop: held {bars_held} bars")

            if direction == "long":
                # Trailing stop trails the HIGHEST close since entry (as designed).
                self._highest_since_entry[symbol] = max(self._highest_since_entry.get(symbol, close), close)
                if close < self._highest_since_entry[symbol] * (1.0 - trailing_pct):
                    return self._make_signal(
                        symbol, SignalAction.SELL, 0.85,
                        f"Trailing stop: close {close:.2f} < high {self._highest_since_entry[symbol]:.2f} × (1-{trailing_pct})",
                    )
            else:
                # Short positions trail the LOWEST close since entry; a short is
                # covered on strength above that floor, not below the peak.
                self._lowest_since_entry[symbol] = min(self._lowest_since_entry.get(symbol, close), close)
                if close > self._lowest_since_entry[symbol] * (1.0 + trailing_pct):
                    return self._make_signal(
                        symbol, SignalAction.BUY_TO_COVER, 0.85,
                        f"Short trailing stop: close {close:.2f} > low {self._lowest_since_entry[symbol]:.2f} × (1+{trailing_pct})",
                    )

            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Holding: bars_held={bars_held}, close={close:.2f}",
            )

        # Entry logic — upside breakout
        if close > high_close + atr and close > sma_trend and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.BUY, confidence=0.6,
                strategy_id=self._strategy_id,
                reason=f"Upside breakout: close {close:.2f} > high({lookback})+ATR = {high_close + atr:.2f}, "
                       f"SMA {sma_trend:.2f}, vol spike",
                metadata={"high_close": round(high_close, 2), "atr": round(atr, 2), "sma": round(sma_trend, 2)},
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "long"
            self._highest_since_entry[symbol] = close
            return signal

        # Entry logic — downside breakout
        if close < low_close - atr and close < sma_trend and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.SELL_SHORT, confidence=0.6,
                strategy_id=self._strategy_id,
                reason=f"Downside breakout: close {close:.2f} < low({lookback})-ATR = {low_close - atr:.2f}, "
                       f"SMA {sma_trend:.2f}, vol spike",
                metadata={"low_close": round(low_close, 2), "atr": round(atr, 2), "sma": round(sma_trend, 2)},
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "short"
            self._lowest_since_entry[symbol] = close
            return signal

        return Signal(
            symbol=symbol, action=SignalAction.HOLD,
            strategy_id=self._strategy_id,
            reason=f"No breakout: close={close:.2f} high({lookback})={high_close:.2f} "
                   f"low({lookback})={low_close:.2f} atr={atr:.2f} holding={holding}",
        )

    def _make_signal(self, symbol: str, action: SignalAction, confidence: float, reason: str) -> Signal:
        signal = Signal(
            symbol=symbol, action=action, confidence=confidence,
            strategy_id=self._strategy_id, reason=reason,
        )
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
