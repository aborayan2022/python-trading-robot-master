"""Extended exception hierarchy for the AI Quant Trading Platform.

Hierarchy:
    PyRobotError
    ├── BrokerError
    │   ├── AuthenticationError
    │   ├── OrderRejectedError
    │   ├── OrderNotFoundError
    │   └── BrokerConnectionError
    ├── RiskError
    │   ├── KillSwitchError
    │   ├── PositionLimitError
    │   ├── DrawdownLimitError
    │   ├── DailyLossLimitError
    │   └── ExposureLimitError
    ├── ExecutionError
    │   ├── DuplicateOrderError
    │   ├── ReconciliationError
    │   └── OrderStateError
    ├── DataError
    │   ├── DataQualityError
    │   └── StaleDataError
    └── ModelError
        ├── ModelDriftError
        └── ModelNotFoundError
"""


# ── Base ──────────────────────────────────────────────────────────────────────

class PyRobotError(Exception):
    """Base exception for all pyrobot errors."""


# ── Broker ────────────────────────────────────────────────────────────────────

class BrokerError(PyRobotError):
    """Raised when a broker API call fails."""


class AuthenticationError(BrokerError):
    """Raised when broker authentication fails."""


class OrderRejectedError(BrokerError):
    """Raised when a broker rejects an order (non-retryable)."""


class OrderNotFoundError(BrokerError):
    """Raised when an order cannot be found."""


class BrokerConnectionError(BrokerError):
    """Raised when the broker connection is lost or unavailable."""


class BrokerRateLimitError(BrokerError):
    """Raised when the broker API rate limit is exceeded (retryable)."""


class BrokerTimeoutError(BrokerError):
    """Raised when a broker API request times out (retryable)."""


# ── Risk ──────────────────────────────────────────────────────────────────────

class RiskError(PyRobotError):
    """Base class for all risk management errors."""


class KillSwitchError(RiskError):
    """Raised when the kill switch is activated.

    This is a hard stop — no new orders may be placed until
    the kill switch is manually reset.
    """

    def __init__(self, reason: str = "Kill switch activated") -> None:
        self.reason = reason
        super().__init__(f"KILL SWITCH ACTIVATED: {reason}")


class PositionLimitError(RiskError):
    """Raised when an order would exceed position size limits."""


class DrawdownLimitError(RiskError):
    """Raised when the portfolio drawdown limit has been breached."""


class DailyLossLimitError(RiskError):
    """Raised when the daily loss limit has been breached."""


class ExposureLimitError(RiskError):
    """Raised when an order would exceed portfolio exposure limits."""


class CorrelationLimitError(RiskError):
    """Raised when adding a position would exceed correlation limits."""


class VolatilityLimitError(RiskError):
    """Raised when market volatility exceeds configured thresholds."""


# ── Execution ─────────────────────────────────────────────────────────────────

class ExecutionError(PyRobotError):
    """Base class for execution engine errors."""


class DuplicateOrderError(ExecutionError):
    """Raised when a duplicate order is detected (same client_order_id)."""


class ReconciliationError(ExecutionError):
    """Raised when order reconciliation with the broker fails."""


class OrderStateError(ExecutionError):
    """Raised when an order is in an unexpected state."""


# ── Data ──────────────────────────────────────────────────────────────────────

class DataError(PyRobotError):
    """Base class for data-related errors."""


class DataQualityError(DataError):
    """Raised when incoming market data fails quality checks."""


class StaleDataError(DataError):
    """Raised when market data is too old to be trusted."""


class DataLeakageError(DataError):
    """Raised when a data leakage / look-ahead bias is detected in features."""


# ── Symbol / Indicator ────────────────────────────────────────────────────────

class InvalidSymbolError(PyRobotError):
    """Raised when an invalid ticker symbol is provided."""


class InvalidIndicatorError(PyRobotError):
    """Raised when indicator parameters are invalid."""


class InsufficientDataError(PyRobotError):
    """Raised when there is not enough data for a calculation."""


# ── Model ─────────────────────────────────────────────────────────────────────

class ModelError(PyRobotError):
    """Base class for ML/AI model errors."""


class ModelDriftError(ModelError):
    """Raised when a model's prediction drift exceeds acceptable thresholds."""


class ModelNotFoundError(ModelError):
    """Raised when a requested model version is not found in the registry."""


class ModelNotApprovedError(ModelError):
    """Raised when attempting to deploy a model without approval."""


# ── Retry helpers ─────────────────────────────────────────────────────────────

#: Exceptions that are safe to retry automatically.
RETRYABLE_EXCEPTIONS = (
    BrokerRateLimitError,
    BrokerTimeoutError,
    BrokerConnectionError,
)

#: Exceptions that must NOT be retried (non-retryable).
NON_RETRYABLE_EXCEPTIONS = (
    OrderRejectedError,
    InvalidSymbolError,
    AuthenticationError,
    KillSwitchError,
    DuplicateOrderError,
)
