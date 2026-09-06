"""US equity trend-following strategy (long-only).

Rules (all confirmed on the bar's close):
  Entry (BUY), only when flat in the symbol:
    - close   > SMA(200)                       long-term uptrend
    - EMA(21) > EMA(50)                        intermediate momentum
    - RSI(14) in [rsi_enter_min, rsi_enter_max]   not oversold / not overheated
    - ATR%    < max_atr_pct                    volatility filter
  Exit (SELL), only when holding:
    - RSI(14) >= rsi_exit                      overbought take-profit
    - close   < EMA(50)                          trend break
    - close   < highest_close_since_entry * (1 - trailing_stop_pct)

The strategy is stateful per symbol: it tracks whether it believes it holds a
position (from on_order_fill callbacks) and the best close since entry for the
trailing stop. Signal action is BUY / SELL / HOLD (never shorting).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pyrobot.indicators import Indicators
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.stock_frame import StockFrame
from pyrobot.strategies.base import MultiSymbolStrategy, StrategyState

logger = get_logger("us_trend")


class USTrendFollowStrategy(MultiSymbolStrategy):
    """Long-only trend + momentum + volatility strategy for liquid US equities."""

    DEFAULT_PARAMETERS = {
        "sma_trend": 200,
        "ema_fast": 21,
        "ema_slow": 50,
        "rsi_period": 14,
        "rsi_enter_min": 45.0,
        "rsi_enter_max": 75.0,
        "rsi_exit": 70.0,
        "atr_period": 14,
        "max_atr_pct": 0.06,
        "trailing_stop_pct": 0.08,
        "min_history_bars": 210,
    }

    def __init__(self, strategy_id: str, symbols: list[str], parameters: Optional[Dict[str, Any]] = None) -> None:
        merged = dict(self.DEFAULT_PARAMETERS)
        if parameters:
            merged.update(parameters)
        super().__init__(strategy_id, symbols, merged)
        self._min_history_bars: int = int(self._parameters["min_history_bars"])
        self._holding: Dict[str, bool] = {s: False for s in self._symbols}
        self._entry_high: Dict[str, float] = {}

    # ── Strategy hooks ───────────────────────────────────────────────────────

    def initialize(self) -> None:
        self._set_state(StrategyState.INITIALIZED)
        logger.info(
            "USTrendFollowStrategy %s initialized: sma=%d ema=%d/%d rsi=%d atr%%_cap=%.2f%% trailing=%.2f%%",
            self._strategy_id,
            self._parameters["sma_trend"],
            self._parameters["ema_fast"],
            self._parameters["ema_slow"],
            self._parameters["rsi_period"],
            self._parameters["max_atr_pct"] * 100.0,
            self._parameters["trailing_stop_pct"] * 100.0,
        )

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        try:
            return self._evaluate(symbol, stock_frame)
        except Exception as exc:
            logger.error("USTrendFollowStrategy.evaluate failed for %s: %s", symbol, exc)
            return Signal(
                symbol=symbol,
                action=SignalAction.NO_TRADE,
                strategy_id=self._strategy_id,
                reason=f"Evaluation error: {exc}",
            )

    def on_order_fill(self, order_dict: dict) -> None:
        """Track holding state from confirmed fills.

        Long-only strategy: while flat only BUY fills arrive (→ enter), while
        holding only SELL fills arrive (→ exit), so the direction is inferred
        from the current state.
        """
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
            self._entry_high.pop(symbol, None)
            self.set_symbol_state(symbol, "holding", False)
        elif direction in ("BUY", "BUY_TO_COVER"):
            self._holding[symbol] = True
            self._entry_high.setdefault(symbol, 0.0)
            self.set_symbol_state(symbol, "holding", True)
        else:
            # No direction in the fill payload: long-only strategy, so a fill
            # toggles holding (flat → filled entry, holding → filled exit).
            if self._holding.get(symbol, False):
                self._holding[symbol] = False
                self._entry_high.pop(symbol, None)
                self.set_symbol_state(symbol, "holding", False)
            else:
                self._holding[symbol] = True
                self._entry_high.setdefault(symbol, 0.0)
                self.set_symbol_state(symbol, "holding", True)
        logger.debug(
            "USTrendFollowStrategy %s fill: %s %s qty=%s holding=%s",
            self._strategy_id, direction or "implicit", symbol, filled_qty, self._holding.get(symbol),
        )

    def get_holding(self, symbol: str) -> bool:
        """Whether the strategy believes it holds this symbol."""
        return bool(self._holding.get(symbol, False))

    # ── Rule evaluation ──────────────────────────────────────────────────────

    def _evaluate(self, symbol: str, stock_frame: StockFrame) -> Signal:
        frame = stock_frame.frame
        has_symbol = symbol in frame.index.get_level_values(0)
        if not has_symbol:
            return Signal(
                symbol=symbol,
                action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"No data yet for {symbol}",
            )

        indicator_client = Indicators(price_data_frame=stock_frame)
        indicator_client.sma(period=int(self._parameters["sma_trend"]), column_name="sma_trend")
        indicator_client.ema(period=int(self._parameters["ema_fast"]), column_name="ema_fast")
        indicator_client.ema(period=int(self._parameters["ema_slow"]), column_name="ema_slow")
        indicator_client.rsi(period=int(self._parameters["rsi_period"]))
        indicator_client.average_true_range(period=int(self._parameters["atr_period"]))

        symbol_rows = frame.xs(symbol, level="symbol")
        if len(symbol_rows) < self._min_history_bars:
            return Signal(
                symbol=symbol,
                action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Warm-up: {len(symbol_rows)} bars < {self._min_history_bars}",
            )

        close = float(symbol_rows["close"].iloc[-1])
        sma_trend = _safe_value(symbol_rows["sma_trend"].iloc[-1])
        ema_fast = _safe_value(symbol_rows["ema_fast"].iloc[-1])
        ema_slow = _safe_value(symbol_rows["ema_slow"].iloc[-1])
        rsi = _safe_value(symbol_rows["rsi"].iloc[-1])
        atr = _safe_value(symbol_rows["average_true_range"].iloc[-1])

        if sma_trend is None or ema_fast is None or ema_slow is None or rsi is None or atr is None:
            return Signal(
                symbol=symbol,
                action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason="Indicators unavailable for latest bar",
            )

        sma_trend = float(sma_trend)
        ema_fast = float(ema_fast)
        ema_slow = float(ema_slow)
        rsi = float(rsi)
        atr = float(atr)

        atr_pct = (atr / close * 100.0) if close > 0 and sma_trend > 0 else 0.0
        rsi_enter_min = float(self._parameters["rsi_enter_min"])
        rsi_enter_max = float(self._parameters["rsi_enter_max"])
        rsi_exit = float(self._parameters["rsi_exit"])
        trailing_pct = float(self._parameters["trailing_stop_pct"])

        holding = self._holding.get(symbol, False)

        # Trailing-stop bookkeeping while holding.
        if holding:
            self._entry_high[symbol] = max(self._entry_high.get(symbol, 0.0), close)

        if holding and (
            (0.0 < sma_trend and close < ema_slow)
            or (0.0 < rsi <= 100.0 and rsi >= rsi_exit)
            or (close < self._entry_high.get(symbol, 0.0) * (1.0 - trailing_pct))
        ):
            signal = Signal(
                symbol=symbol,
                action=SignalAction.SELL,
                confidence=0.8,
                strategy_id=self._strategy_id,
                reason=self._exit_reason(close, ema_slow, rsi, rsi_exit),
                metadata={
                    "sma_trend": round(sma_trend, 4) if sma_trend else None,
                    "ema_fast": round(ema_fast, 4),
                    "ema_slow": round(ema_slow, 4),
                    "rsi": round(rsi, 4),
                    "atr_pct": round(atr_pct, 4),
                },
            )
        elif not holding and _finites(sma_trend, ema_fast, ema_slow, rsi, atr) and (
            close > sma_trend > 0
            and ema_fast > ema_slow
            and rsi_enter_min <= rsi <= rsi_enter_max
            and 0.0 < atr_pct < float(self._parameters["max_atr_pct"]) * 100.0
        ):
            signal = Signal(
                symbol=symbol,
                action=SignalAction.BUY,
                confidence=0.62,
                strategy_id=self._strategy_id,
                reason=(
                    f"Uptrend: close {close:.2f} > SMA{int(self._parameters['sma_trend'])} "
                    f"({sma_trend:.2f}), EMA{int(self._parameters['ema_fast'])} > "
                    f"EMA{int(self._parameters['ema_slow'])}, RSI {rsi:.1f} in "
                    f"[{rsi_enter_min:.0f},{rsi_enter_max:.0f}], ATR% {atr_pct:.2f}%"
                ),
                metadata={
                    "sma_trend": round(sma_trend, 4),
                    "ema_fast": round(ema_fast, 4),
                    "ema_slow": round(ema_slow, 4),
                    "rsi": round(rsi, 4),
                    "atr_pct": round(atr_pct, 4),
                },
            )
        else:
            signal = Signal(
                symbol=symbol,
                action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"No signal: close={close:.2f} sma={sma_trend:.2f} ema_f={ema_fast:.2f} "
                f"ema_s={ema_slow:.2f} rsi={rsi:.1f} atr%={atr_pct:.2f}% holding={holding}",
                metadata={
                    "sma_trend": round(sma_trend, 4) if sma_trend else None,
                    "ema_fast": round(ema_fast, 4),
                    "ema_slow": round(ema_slow, 4),
                    "rsi": round(rsi, 4),
                    "atr_pct": round(atr_pct, 4),
                },
            )

        self._record_signal(signal)
        self._set_state(StrategyState.RUNNING)
        return signal

    def _exit_reason(self, close: float, ema_slow: float, rsi: float, rsi_exit: float) -> str:
        if ema_slow > 0 and close < ema_slow:
            return f"Trend break: close {close:.2f} < EMA{int(self._parameters['ema_slow'])} {ema_slow:.2f}"
        if 0.0 < rsi <= 100.0 and rsi >= rsi_exit:
            return f"Overbought: RSI {rsi:.1f} >= {rsi_exit:.0f}"
        return f"Trailing stop hit: close {close:.2f} < high*(1-{self._parameters['trailing_stop_pct']})"


def _safe_value(value) -> Optional[float]:
    """Convert possibly-NaN indicator cell to float (None when invalid)."""
    if value is None:
        return None
    try:
        import math

        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def _finites(*values: Optional[float]) -> bool:
    return all(v is not None for v in values)
