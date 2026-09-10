"""Crypto mean reversion strategy (long + short).

Exploits extreme RSI and Bollinger Band deviations in high-volatility crypto
markets. Crypto's tendency to overextend and snap back makes mean reversion
profitable when combined with strict risk controls.

Rules:
  Entry (BUY):
    - RSI(14) < 25                             deeply oversold
    - close < lower_bollinger(20, 2.5)         2.5σ below mean
    - volume > avg_volume × 2.0                capitulation selling
  Entry (SELL_SHORT):
    - RSI(14) > 75                             deeply overbought
    - close > upper_bollinger(20, 2.5)         2.5σ above mean
    - volume > avg_volume × 2.0                euphoric buying
  Exit:
    - Close crosses SMA(20)                    mean reversion target
    - Time stop (max 7 bars — crypto reverts fast)
    - Stop loss (5%)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from pyrobot.indicators import Indicators
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.stock_frame import StockFrame
from pyrobot.strategies.base import MultiSymbolStrategy, StrategyState

logger = get_logger("crypto_mean_rev")


class CryptoMeanReversionStrategy(MultiSymbolStrategy):
    """Mean reversion strategy for cryptocurrency — long and short."""

    DEFAULT_PARAMETERS = {
        "rsi_period": 14,
        "rsi_buy_threshold": 25.0,
        "rsi_sell_threshold": 75.0,
        "bb_period": 20,
        "bb_std": 2.5,
        "sma_period": 20,
        "volume_mult": 2.0,
        "stop_loss_pct": 0.05,
        "max_holding_days": 7,
        "min_history_bars": 30,
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
        self._bar_count: int = 0

    def initialize(self) -> None:
        self._set_state(StrategyState.INITIALIZED)
        logger.info(
            "CryptoMeanReversionStrategy %s initialized: rsi_buy=%s rsi_sell=%s bb=%.1f std stop=%.1f%%",
            self._strategy_id,
            self._parameters["rsi_buy_threshold"],
            self._parameters["rsi_sell_threshold"],
            self._parameters["bb_std"],
            self._parameters["stop_loss_pct"] * 100,
        )

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        try:
            self._bar_count += 1
            return self._evaluate(symbol, stock_frame)
        except Exception as exc:
            logger.error("CryptoMeanReversionStrategy.evaluate failed for %s: %s", symbol, exc)
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
            self.set_symbol_state(symbol, "holding", False)
        elif direction in ("BUY", "BUY_TO_COVER"):
            self._holding[symbol] = True
            self._entry_bar_idx[symbol] = self._bar_count
            self.set_symbol_state(symbol, "holding", True)
        else:
            if self._holding.get(symbol, False):
                self._holding[symbol] = False
                self._holding_direction[symbol] = "flat"
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
        indicator_client.rsi(period=int(self._parameters["rsi_period"]))
        indicator_client.sma(period=int(self._parameters["sma_period"]), column_name="sma_mean")

        symbol_rows = frame.xs(symbol, level="symbol")
        if len(symbol_rows) < self._min_history_bars:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Warm-up: {len(symbol_rows)} bars < {self._min_history_bars}",
            )

        close = float(symbol_rows["close"].iloc[-1])
        rsi_val = _safe_value(symbol_rows["rsi"].iloc[-1])
        sma_val = _safe_value(symbol_rows["sma_mean"].iloc[-1])

        if rsi_val is None or sma_val is None:
            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id, reason="Indicators unavailable",
            )

        rsi = float(rsi_val)
        sma = float(sma_val)

        closes = symbol_rows["close"].astype(float)
        bb_std_val = float(self._parameters["bb_std"])
        rolling_std = closes.rolling(int(self._parameters["bb_period"])).std().iloc[-1]
        rolling_std = float(rolling_std) if not np.isnan(rolling_std) else 0.0
        upper_bb = sma + bb_std_val * rolling_std
        lower_bb = sma - bb_std_val * rolling_std

        volumes = symbol_rows["volume"].astype(float)
        avg_vol = float(volumes.rolling(20).mean().iloc[-1]) if len(volumes) >= 20 else float(volumes.mean())
        current_vol = float(volumes.iloc[-1])
        volume_ok = current_vol > avg_vol * float(self._parameters["volume_mult"])

        holding = self._holding.get(symbol, False)

        # Exit
        if holding:
            entry_bar = self._entry_bar_idx.get(symbol, 0)
            bars_held = self._bar_count - entry_bar
            if bars_held > int(self._parameters["max_holding_days"]):
                action = SignalAction.SELL if self._holding_direction.get(symbol) == "long" else SignalAction.BUY_TO_COVER
                return self._make_signal(symbol, action, 0.9, f"Time stop: held {bars_held} bars")

            if sma > 0 and abs(close - sma) / sma < 0.01:
                action = SignalAction.SELL if self._holding_direction.get(symbol) == "long" else SignalAction.BUY_TO_COVER
                return self._make_signal(symbol, action, 0.85,
                    f"Crypto mean reversion: close {close:.2f} ≈ SMA {sma:.2f}")

            return Signal(
                symbol=symbol, action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Holding: bars_held={bars_held}, close={close:.2f}, rsi={rsi:.1f}",
            )

        # Long entry
        if rsi < float(self._parameters["rsi_buy_threshold"]) and close < lower_bb and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.BUY, confidence=0.6,
                strategy_id=self._strategy_id,
                reason=f"Crypto mean reversion BUY: RSI {rsi:.1f} < {self._parameters['rsi_buy_threshold']}, "
                       f"close {close:.2f} < BB_lower {lower_bb:.2f}",
                metadata={"rsi": round(rsi, 2), "bb_lower": round(lower_bb, 2), "sma": round(sma, 2)},
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "long"
            return signal

        # Short entry
        if rsi > float(self._parameters["rsi_sell_threshold"]) and close > upper_bb and volume_ok:
            signal = Signal(
                symbol=symbol, action=SignalAction.SELL_SHORT, confidence=0.6,
                strategy_id=self._strategy_id,
                reason=f"Crypto mean reversion SELL_SHORT: RSI {rsi:.1f} > {self._parameters['rsi_sell_threshold']}, "
                       f"close {close:.2f} > BB_upper {upper_bb:.2f}",
                metadata={"rsi": round(rsi, 2), "bb_upper": round(upper_bb, 2), "sma": round(sma, 2)},
            )
            self._record_signal(signal)
            self._set_state(StrategyState.RUNNING)
            self._holding_direction[symbol] = "short"
            return signal

        return Signal(
            symbol=symbol, action=SignalAction.HOLD,
            strategy_id=self._strategy_id,
            reason=f"No signal: RSI={rsi:.1f} close={close:.2f} sma={sma:.2f} holding={holding}",
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
