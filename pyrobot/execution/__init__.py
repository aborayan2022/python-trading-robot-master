"""Execution Engine package.

Provides the full order submission pipeline:

    Signal
      → ExecutionEngine.submit(signal)
      → KillSwitch.guard()
      → RiskEngine (future)
      → OrderManager.create(order)
      → Broker.place_order(order)
      → OrderManager.track(order)
      → Reconciliation (async)
"""
from pyrobot.execution.engine import ExecutionEngine
from pyrobot.execution.order_manager import OrderManager
from pyrobot.execution.reconciliation import OrderReconciler

__all__ = ["ExecutionEngine", "OrderManager", "OrderReconciler"]
