"""Crypto trend/volatility breakout strategy (long + short).

Designed for high-volatility 24/7 crypto markets. Uses wider stops and
volatility-adaptive entries.

Rules:
  Entry (BUY):
    - close > highest_close(lookback) + 1.5×ATR   strong upside breakout
    - volume > avg_volume × 2.0                    high participation
    - close > EMA(50)                              trend alignment
  Entry (SELL_SHORT):
    - close < lowest_close(lookback) - 1.5×ATR     strong downside breakdown
    - volume > avg_volume × 2.0                    selling pressure
    - close < EMA(50)                              trend alignment
  Exit:
    - Trailing stop (3× ATR — wider for crypto volatility)
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

logger = get_logger("crypto_trend")


class CryptoTrendBreakoutStrategy(MultiSymbolStrategy):
    """Trend/volatility breakout strategy for cryptocurrency — long and short."""

    DEFAULT_PARAMETERS = {
        "lookback": 20,
        "atr_period": 14,
        "ema_trend": 50,
        "breakout_atr_mult": 1.5,
        "volume_mult": 2.0,
        "trailing_stop_atr_mult": 3.0,
        "max_holding_days": 15,
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
        self._entry_bar_idx: Dict[str, int] = {s: 0 for s in self._symbols}
        self._entry_price: Dict[str, float] = {}
        self._stop_level: Dict[str, float] = {}
        self._extreme_high: Dict[str, float] = {}
        self._extreme_low: Dict[str, float] = {}
        self._bar_count: Dict[str, int] = {s: 0 for s in self._symbols}

    def initialize(self) -> None:
        self._set_state(StrategyState.INITIALIZED)
        logger.info(
            "CryptoTrendBreakoutStrategy %s initialized: lookback=%d atr_mult=%.1f trail=%.1f",
            self._strategy_id,
            self._parameters["breakout_atr_mult"],
            self._parameters["trailing_stop_atr_mult"],
        )

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        try:
            self._bar_count[symbol] += 1
            return self._evaluate(symbol, stock_frame)
        except Exception as exc:
            logger.error("CryptoTrendBreakoutStrategy.evaluate failed for %s: %s", symbol, exc)
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
            self._entry_price[symbol] = _fill_price(order_dict, self._entry_price.get(symbol))
            self._stop_level.pop(symbol, None)
            self._extreme_high.pop(symbol, None)
            self._extreme_low.pop(symbol, None)
            self.set_symbol_state(symbol, "holding", True)
        elif direction in ("SELL", "BUY_TO_COVER"):
            self._holding[symbol] = False
            self._holding_direction[symbol] = "flat"
            self._entry_price.pop(symbol, None)
            self._stop_level.pop(symbol, None)
            self._extreme_high.pop(symbol, None)
            self._extreme_low.pop(symbol, None)
            self.set_symbol_state(symbol, "holding", False)
        else:
            if self._holding.get(symbol, False):
                self._holding[symbol] = False
                self._holding_direction[symbol] = "flat"
                self._entry_price.pop(symbol, None)
                self._stop_level.pop(symbol, None)
                self._extreme_high.pop(symbol, None)
                self._extreme_low.pop(symbol, None)
                self.set_symbol_state(symbol, "holding", False)
            else:
                self._holding[symbol] = True
                self._entry_bar_idx[symbol] = self._bar_count[symbol]
                self._entry_price[symbol] = _fill_price(order_dict, self._entry_price.get(symbol))
                self._stop_level.pop(symbol, None)
                self._extreme_high.pop(symbol, None)
                self._extreme_low.pop(symbol, None)
                self.set_symbol_state(symbol, "holding", True)

    def get_holding(self, symbol: str) -> bool:
        return bool(self._holding.get(symbol, False))

    def sync_positions(self, positions: Dict[str, float]) -> None:
        """Synchronize holding/direction state with a broker position snapshot.

        Positive quantity → long, negative quantity → short, zero → flat.
        Time-stop bars are restarted from the current bar on sync; the
        ratcheted trailing stop re-seeds from the first bar after sync.

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
                self._entry_price.pop(symbol, None)
                self._stop_level.pop(symbol, None)
                self._extreme_high.pop(symbol, None)
                self._extreme_low.pop(symbol, None)
            else:
                self._entry_bar_idx[symbol] = self._bar_count.get(symbol, 0)
                self._stop_level.pop(symbol, None)
                self._extreme_high.pop(symbol, None)
                self._extreme_low.pop(symbol, None)
            self.set_symbol_state(symbol, "holding", qty != 0.0)
            logger.info(
                "CryptoTrendBreakoutStrategy %s synced position for %s: qty=%s holding=%s direction=%s",
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
        indicator_client.ema(period=int(self._parameters["ema_trend"]), column_name="ema_trend")
        indicator_client.average_true_range(period=int(self._parameters["atr_period"]))

        symbol_rows = frame.xs(symbol, level="symbol")
        if len(symbol_rows) < self._min_history_bars:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Warm-up: {len(symbol_rows)} bars < {self._min_history_bars}",
            )

        close = float(symbol_rows["close"].iloc[-1])
        ema = _safe_value(symbol_rows["ema_trend"].iloc[-1])
        atr = _safe_value(symbol_rows["average_true_range"].iloc[-1])

        if ema is None or atr is None:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id, reason="Indicators unavailable",
            )

        ema, atr = float(ema), float(atr)
        lookback = int(self._parameters["lookback"])
        closes = symbol_rows["close"].astype(float)
        high_close = float(closes.iloc[-(lookback + 1):-1].max()) if len(closes) > lookback else float(closes.iloc[-lookback:].max())
        low_close = float(closes.iloc[-(lookback + 1):-1].min()) if len(closes) > lookback else float(closes.iloc[-lookback:].min())

        volumes = symbol_rows["volume"].astype(float)
        avg_vol = float(volumes.rolling(20).mean().iloc[-1]) if len(volumes) >= 20 else float(volumes.mean())
        current_vol = float(volumes.iloc[-1])
        volume_ok = current_vol > avg_vol * float(self._parameters["volume_mult"])

        holding = self._holding.get(symbol, False)
        breakout_mult = float(self._parameters["breakout_atr_mult"])
        trail_mult = float(self._parameters["trailing_stop_atr_mult"])

        # Exit
        if holding:
            entry_bar = self._entry_bar_idx.get(symbol, 0)
            bars_held = self._bar_count.get(symbol, 0) - entry_bar
            if bars_held > int(self._parameters["max_holding_days"]):
                action = SignalAction.SELL if self._holding_direction.get(symbol) == "long" else SignalAction.BUY_TO_COVER
                return self._make_signal(symbol, action, 0.9, f"Time stop: held {bars_held} bars")

            # Trailing stop anchored to the actual fill price and ratcheted off
            # the running high/low since entry: it protects realized gains and
            # never drifts back toward the signal close as ATR changes.
            entry_p = self._entry_price.get(symbol, close)
            if self._holding_direction.get(symbol) == "long":
                self._extreme_high[symbol] = max(self._extreme_high.get(symbol, entry_p), close)
                candidate = self._extreme_high[symbol] - trail_mult * atr
                self._stop_level[symbol] = max(self._stop_level.get(symbol, candidate), candidate)
                if close < self._stop_level[symbol]:
                    return self._make_signal(symbol, SignalAction.SELL, 0.85,
                        f"Crypto ATR trailing stop: close {close:.2f} < stop {self._stop_level[symbol]:.2f} (from high {self._extreme_high[symbol]:.2f}, entry {entry_p:.2f})")
            else:
                self._extreme_low[symbol] = min(self._extreme_low.get(symbol, entry_p), close)
                candidate = self._extreme_low[symbol] + trail_mult * atr
                self._stop_level[symbol] = min(self._stop_level.get(symbol, candidate), candidate)
                if close > self._stop_level[symbol]:
                    return self._make_signal(symbol, SignalAction.BUY_TO_COVER, 0.85,
                        f"Crypto ATR trailing stop: close {close:.2f} > stop {self._stop_level[symbol]:.2f} (from low {self._extreme_low[symbol]:.2f}, entry {entry_p:.2f})")

            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Holding: bars_held={bars_held}, close={close:.2f}",
            )

        # Long entry
        if close > high_close + breakout_mult * atr and close > ema and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.BUY, confidence=0.55,
                strategy_id=self._strategy_id,
                reason=f"Crypto upside breakout: close {close:.2f} > {high_close:.2f}+{breakout_mult}×ATR, "
                       f"EMA {ema:.2f}, vol spike",
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "long"
            self._entry_price[symbol] = close
            return signal

        # Short entry
        if close < low_close - breakout_mult * atr and close < ema and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.SELL_SHORT, confidence=0.55,
                strategy_id=self._strategy_id,
                reason=f"Crypto downside breakout: close {close:.2f} < {low_close:.2f}-{breakout_mult}×ATR, "
                       f"EMA {ema:.2f}, vol spike",
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


def _fill_price(order_dict: dict, default: Optional[float] = None) -> Optional[float]:
    """Extract the actual fill price from an order dict when present.

    Post-trade callbacks carry the real execution price (``fill_price`` or
    ``avg_fill_price``); the strategy records it so the ATR trailing stop is
    anchored to the true entry cost rather than the signal bar's close.
    """
    for key in ("fill_price", "avg_fill_price"):
        raw = order_dict.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return default


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
