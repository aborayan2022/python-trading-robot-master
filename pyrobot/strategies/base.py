"""Strategy Engine - base classes for all trading strategies."""

import threading
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from enum import Enum
from typing import Any, Dict, List, Optional

from pyrobot.indicators import Indicators
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.stock_frame import StockFrame

logger = get_logger("strategies")


class StrategyState(str, Enum):
    CREATED = "CREATED"
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies.

    Provides thread-safe state management, lifecycle hooks, and
    a standard interface for the strategy engine to drive.
    """

    def __init__(self, strategy_id: str, symbols: List[str], parameters: Dict[str, Any] = None) -> None:
        self._strategy_id = strategy_id
        self._symbols = list(symbols)
        self._parameters = dict(parameters) if parameters else {}
        self._state = StrategyState.CREATED
        self._lock = threading.Lock()
        self._error: Optional[Exception] = None

        logger.info(
            "Strategy %s created for symbols=%s",
            self._strategy_id,
            self._symbols,
        )

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def symbols(self) -> List[str]:
        return list(self._symbols)

    @property
    def parameters(self) -> Dict[str, Any]:
        return dict(self._parameters)

    @property
    def state(self) -> StrategyState:
        with self._lock:
            return self._state

    def _set_state(self, new_state: StrategyState) -> None:
        with self._lock:
            old = self._state
            self._state = new_state
        logger.info("Strategy %s state: %s -> %s", self._strategy_id, old, new_state)

    @abstractmethod
    def initialize(self) -> None:
        """Set up indicators, load models, prepare internal state."""
        ...

    @abstractmethod
    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        """Process a new bar and return a Signal."""
        ...

    @abstractmethod
    def on_order_fill(self, order_dict: dict) -> None:
        """React to an order fill notification."""
        ...

    def on_start(self) -> None:
        """Called when the strategy transitions to RUNNING."""
        pass

    def on_stop(self) -> None:
        """Called when the strategy is stopped."""
        pass

    def on_error(self, error: Exception) -> None:
        """Called when an error occurs during execution."""
        pass

    def supports_symbol(self, symbol: str) -> bool:
        return symbol in self._symbols


class MultiSymbolStrategy(BaseStrategy):
    """Strategy that tracks per-symbol state: signals history and indicators.

    Subclasses only need to implement `on_bar` for per-symbol logic.
    """

    def __init__(self, strategy_id: str, symbols: List[str], parameters: Dict[str, Any] = None) -> None:
        super().__init__(strategy_id, symbols, parameters)
        self._recent_signals: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._indicators: Dict[str, Indicators] = {}
        self._symbol_state: Dict[str, Dict[str, Any]] = defaultdict(dict)

    @property
    def indicators(self) -> Dict[str, Indicators]:
        return dict(self._indicators)

    def get_symbol_state(self, symbol: str) -> Dict[str, Any]:
        return dict(self._symbol_state[symbol])

    def set_symbol_state(self, symbol: str, key: str, value: Any) -> None:
        self._symbol_state[symbol][key] = value

    def get_recent_signals(self, symbol: str, n: int = 10) -> List[Signal]:
        with self._lock:
            signals = list(self._recent_signals[symbol])
        return signals[-n:]

    def _record_signal(self, signal: Signal) -> None:
        with self._lock:
            self._recent_signals[signal.symbol].append(signal)

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        signal = Signal(
            symbol=symbol,
            action=SignalAction.NO_TRADE,
            strategy_id=self._strategy_id,
            reason="BaseMultiSymbolStrategy default: no logic implemented",
        )
        self._record_signal(signal)
        return signal


class ExampleStrategy(MultiSymbolStrategy):
    """Simple SMA crossover strategy for testing.

    BUY when fast SMA crosses above slow SMA.
    SELL when fast SMA crosses below slow SMA.
    HOLD otherwise.
    """

    DEFAULT_PARAMETERS = {
        "fast_period": 10,
        "slow_period": 30,
    }

    def __init__(self, strategy_id: str, symbols: List[str], parameters: Dict[str, Any] = None) -> None:
        merged = dict(self.DEFAULT_PARAMETERS)
        if parameters:
            merged.update(parameters)
        super().__init__(strategy_id, symbols, merged)
        self._fast_period: int = self._parameters["fast_period"]
        self._slow_period: int = self._parameters["slow_period"]

    def initialize(self) -> None:
        self._set_state(StrategyState.INITIALIZED)
        logger.info(
            "ExampleStrategy %s initialized: fast=%d slow=%d",
            self._strategy_id,
            self._fast_period,
            self._slow_period,
        )

    def on_bar(self, symbol: str, bar: dict, stock_frame: StockFrame) -> Signal:
        indicator_client = Indicators(price_data_frame=stock_frame)
        indicator_client.sma(period=self._fast_period, column_name="sma_fast")
        indicator_client.sma(period=self._slow_period, column_name="sma_slow")

        frame = stock_frame.frame
        if symbol not in frame.index.get_level_values(0):
            signal = Signal(
                symbol=symbol,
                action=SignalAction.NO_TRADE,
                strategy_id=self._strategy_id,
                reason=f"No data for {symbol}",
            )
            self._record_signal(signal)
            return signal

        symbol_data = frame.loc[symbol]
        if len(symbol_data) < self._slow_period:
            signal = Signal(
                symbol=symbol,
                action=SignalAction.HOLD,
                strategy_id=self._strategy_id,
                reason=f"Insufficient bars ({len(symbol_data)} < {self._slow_period})",
            )
            self._record_signal(signal)
            return signal

        sma_fast = symbol_data["sma_fast"]
        sma_slow = symbol_data["sma_slow"]
        last_fast = sma_fast.iloc[-1]
        last_slow = sma_slow.iloc[-1]
        prev_fast = sma_fast.iloc[-2] if len(sma_fast) > 1 else last_fast
        prev_slow = sma_slow.iloc[-2] if len(sma_slow) > 1 else last_slow

        if last_fast > last_slow and prev_fast <= prev_slow:
            action = SignalAction.BUY
            reason = f"Fast SMA ({last_fast:.4f}) crossed above slow SMA ({last_slow:.4f})"
        elif last_fast < last_slow and prev_fast >= prev_slow:
            action = SignalAction.SELL
            reason = f"Fast SMA ({last_fast:.4f}) crossed below slow SMA ({last_slow:.4f})"
        else:
            action = SignalAction.HOLD
            reason = f"No crossover: fast={last_fast:.4f}, slow={last_slow:.4f}"

        signal = Signal(
            symbol=symbol,
            action=action,
            confidence=0.75 if action != SignalAction.HOLD else 0.0,
            strategy_id=self._strategy_id,
            reason=reason,
            metadata={
                "sma_fast": last_fast,
                "sma_slow": last_slow,
                "fast_period": self._fast_period,
                "slow_period": self._slow_period,
            },
        )

        self._record_signal(signal)
        self._set_state(StrategyState.RUNNING)
        return signal

    def on_order_fill(self, order_dict: dict) -> None:
        logger.info("ExampleStrategy %s order filled: %s", self._strategy_id, order_dict)
