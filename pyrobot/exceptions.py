"""Custom exception hierarchy for the trading robot."""


class PyRobotError(Exception):
    """Base exception for all pyrobot errors."""


class BrokerError(PyRobotError):
    """Raised when a broker API call fails."""


class AuthenticationError(BrokerError):
    """Raised when broker authentication fails."""


class OrderRejectedError(BrokerError):
    """Raised when a broker rejects an order."""


class OrderNotFoundError(BrokerError):
    """Raised when an order cannot be found."""


class InvalidSymbolError(PyRobotError):
    """Raised when an invalid ticker symbol is provided."""


class InvalidIndicatorError(PyRobotError):
    """Raised when indicator parameters are invalid."""


class InsufficientDataError(PyRobotError):
    """Raised when there is not enough data for a calculation."""
