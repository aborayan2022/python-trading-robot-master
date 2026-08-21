"""Risk decision model for pre-trade risk checks."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class RiskDecision:
    """Represents the explicit evaluation outcome of a pre-trade risk check.

    Attributes:
        approved: True if the order passes all risk constraints.
        reason: Human-readable explanation or rejection reason.
        order_id: The client_order_id of the evaluated order.
        symbol: Ticker symbol.
        timestamp: UTC timestamp of the evaluation.
        checks_passed: List of risk rules/checks that passed.
        checks_failed: List of risk rules/checks that failed.
        metrics: Snapshot of risk metrics at evaluation time (exposure, drawdown, etc.).
        adjusted_quantity: Suggested position-sized quantity (if scaled/adjusted).
    """

    approved: bool
    reason: str
    order_id: str
    symbol: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    adjusted_quantity: Optional[float] = None

    def to_dict(self) -> Dict:
        """Serialize risk decision to dict."""
        return {
            "approved": self.approved,
            "reason": self.reason,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "metrics": self.metrics,
            "adjusted_quantity": self.adjusted_quantity,
        }
