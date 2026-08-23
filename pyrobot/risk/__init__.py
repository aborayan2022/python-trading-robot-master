"""Risk Engine package.

Provides:
    - KillSwitch: Hard stop for all trading activity.
    - RiskManager: Central orchestration for all risk management.
    - RiskLimits: Configurable risk parameters.
    - PositionSizer: Kelly and fixed-fraction position sizing.
    - ExposureMonitor: Portfolio exposure tracking and limits.
    - DrawdownMonitor: Drawdown protection.
    - CircuitBreaker: Automatic trading halt after consecutive failures.
"""
from pyrobot.risk.circuit_breaker import CircuitBreaker, CircuitState
from pyrobot.risk.decision import RiskDecision
from pyrobot.risk.drawdown import DrawdownMonitor
from pyrobot.risk.exposure import ExposureMonitor, ExposureSnapshot
from pyrobot.risk.kill_switch import KillSwitch, KillSwitchReason
from pyrobot.risk.limits import RiskLimits
from pyrobot.risk.manager import RiskManager
from pyrobot.risk.position_sizer import PositionSizer

__all__ = [
    "KillSwitch",
    "KillSwitchReason",
    "RiskLimits",
    "RiskManager",
    "RiskDecision",
    "PositionSizer",
    "ExposureMonitor",
    "ExposureSnapshot",
    "DrawdownMonitor",
    "CircuitBreaker",
    "CircuitState",
]
