"""Canonical Signal model for strategy outputs."""

import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class SignalAction(Enum):
    """Signal action types."""

    BUY = "BUY"
    SELL = "SELL"
    SELL_SHORT = "SELL_SHORT"
    BUY_TO_COVER = "BUY_TO_COVER"
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"


@dataclass
class Signal:
    """Canonical signal model produced by strategies.

    A signal represents a trading decision before risk validation
    and position sizing. The signal flows through:
        Signal → Risk Engine → Position Sizing → Execution

    Attributes:
        symbol: Ticker symbol.
        action: The recommended action.
        probability: Model probability for this signal (0.0 to 1.0).
        confidence: Strategy confidence in this signal (0.0 to 1.0).
        timestamp: When the signal was generated (UTC).
        strategy_id: Identifier of the strategy that generated this signal.
        model_id: Identifier of the model (if ML-based).
        reason: Human-readable reason for the signal.
        expected_return: Expected return for this trade.
        expected_risk: Expected risk for this trade.
        metadata: Additional strategy-specific data.
    """

    symbol: str
    action: SignalAction
    probability: float = 0.0
    confidence: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_id: Optional[str] = None
    model_id: Optional[str] = None
    reason: Optional[str] = None
    expected_return: Optional[float] = None
    expected_risk: Optional[float] = None
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Check if this signal requires execution action."""
        return self.action in {
            SignalAction.BUY,
            SignalAction.SELL,
            SignalAction.SELL_SHORT,
            SignalAction.BUY_TO_COVER,
        }

    @property
    def risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio if both are available."""
        if self.expected_return is not None and self.expected_risk is not None:
            if self.expected_risk != 0:
                return abs(self.expected_return / self.expected_risk)
        return None

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return {
            "symbol": self.symbol,
            "action": self.action.value,
            "probability": self.probability,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "strategy_id": self.strategy_id,
            "model_id": self.model_id,
            "reason": self.reason,
            "expected_return": self.expected_return,
            "expected_risk": self.expected_risk,
            "signal_id": self.signal_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_legacy_action(cls, symbol: str, action: str, **kwargs) -> "Signal":
        """Create a Signal from a legacy action string.

        Maps legacy 'buy'/'sell'/None actions to SignalAction.
        """
        action_map = {
            "buy": SignalAction.BUY,
            "sell": SignalAction.SELL,
            "sell_short": SignalAction.SELL_SHORT,
            "buy_to_cover": SignalAction.BUY_TO_COVER,
            "hold": SignalAction.HOLD,
        }
        signal_action = action_map.get(action.lower() if action else "", SignalAction.NO_TRADE)

        return cls(
            symbol=symbol,
            action=signal_action,
            **kwargs,
        )
