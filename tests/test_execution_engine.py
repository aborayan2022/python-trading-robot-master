"""Tests for pyrobot.execution — ExecutionEngine and OrderManager."""

import pytest
from unittest.mock import MagicMock, patch

from pyrobot.exceptions import (
    KillSwitchError,
    DuplicateOrderError,
    ExecutionError,
    OrderRejectedError,
    OrderStateError,
)
from pyrobot.execution.engine import ExecutionEngine
from pyrobot.execution.order_manager import OrderManager
from pyrobot.execution.reconciliation import OrderReconciler
from pyrobot.models.order import Order, OrderSide, OrderType, TimeInForce, OrderState
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.risk.kill_switch import KillSwitch, KillSwitchReason


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def kill_switch() -> KillSwitch:
    return KillSwitch()


@pytest.fixture
def order_manager() -> OrderManager:
    return OrderManager()


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.place_order.return_value = {
        "order_id": "broker-001",
        "status": "SUBMITTED",
        "request_body": {},
    }
    broker.get_order_status.return_value = {
        "order_id": "broker-001",
        "status": "filled",
        "filled_quantity": 10.0,
        "avg_fill_price": 150.0,
    }
    return broker


@pytest.fixture
def engine(mock_broker, order_manager, kill_switch) -> ExecutionEngine:
    return ExecutionEngine(
        broker=mock_broker,
        order_manager=order_manager,
        kill_switch=kill_switch,
        account_id="TEST_ACCOUNT",
        max_retries=1,
    )


@pytest.fixture
def buy_signal() -> Signal:
    return Signal(
        symbol="AAPL",
        action=SignalAction.BUY,
        probability=0.78,
        confidence=0.82,
        strategy_id="trend_v1",
    )


@pytest.fixture
def buy_order(order_manager, buy_signal) -> Order:
    return order_manager.create_from_signal(buy_signal, quantity=10)


# ══════════════════════════════════════════════════════════════════════════════
# OrderManager Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderManager:

    def test_create_from_signal_returns_order(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == 5
        assert order.status == OrderState.NEW
        assert order.strategy_id == "trend_v1"

    def test_create_from_signal_links_signal_id(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        assert order.signal_id == buy_signal.signal_id

    def test_create_from_non_actionable_signal_raises(self, order_manager):
        hold_signal = Signal(symbol="AAPL", action=SignalAction.HOLD)
        with pytest.raises(ValueError, match="not actionable"):
            order_manager.create_from_signal(hold_signal, quantity=1)

    def test_no_trade_signal_raises(self, order_manager):
        no_trade = Signal(symbol="MSFT", action=SignalAction.NO_TRADE)
        with pytest.raises(ValueError):
            order_manager.create_from_signal(no_trade, quantity=1)

    def test_duplicate_client_order_id_raises(self, order_manager, buy_signal):
        coid = "fixed-coid-001"
        order_manager.create_from_signal(buy_signal, quantity=5, client_order_id=coid)
        with pytest.raises(DuplicateOrderError):
            order_manager.create_from_signal(buy_signal, quantity=5, client_order_id=coid)

    def test_lifecycle_new_to_submitted(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        order_manager.mark_submitted(order.client_order_id, "broker-abc")
        assert order.status == OrderState.SUBMITTED
        assert order.broker_order_id == "broker-abc"

    def test_lifecycle_submitted_to_filled(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        order_manager.mark_submitted(order.client_order_id, "broker-abc")
        order_manager.mark_filled(order.client_order_id, 5.0, 150.0)
        assert order.status == OrderState.FILLED
        assert order.filled_quantity == 5.0
        assert order.avg_fill_price == 150.0

    def test_invalid_state_transition_raises(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        # NEW → FILLED is not valid (must go through SUBMITTED first)
        with pytest.raises(OrderStateError):
            order_manager.mark_filled(order.client_order_id, 5.0, 100.0)

    def test_mark_unknown_sets_state(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        order_manager.mark_submitted(order.client_order_id, "broker-xyz")
        order_manager.mark_unknown(order.client_order_id, "connection lost")
        assert order.status == OrderState.UNKNOWN

    def test_unknown_orders_returns_correct_list(self, order_manager):
        s1 = Signal(symbol="AAPL", action=SignalAction.BUY)
        s2 = Signal(symbol="MSFT", action=SignalAction.BUY)
        o1 = order_manager.create_from_signal(s1, quantity=5)
        o2 = order_manager.create_from_signal(s2, quantity=3)
        order_manager.mark_submitted(o1.client_order_id, "b1")
        order_manager.mark_submitted(o2.client_order_id, "b2")
        order_manager.mark_unknown(o1.client_order_id)
        unknown = order_manager.unknown_orders()
        assert len(unknown) == 1
        assert unknown[0].symbol == "AAPL"

    def test_get_by_broker_id(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        order_manager.mark_submitted(order.client_order_id, "broker-999")
        found = order_manager.get_by_broker_id("broker-999")
        assert found is not None
        assert found.client_order_id == order.client_order_id

    def test_active_orders_excludes_terminal(self, order_manager):
        s1 = Signal(symbol="AAPL", action=SignalAction.BUY)
        s2 = Signal(symbol="MSFT", action=SignalAction.SELL)
        o1 = order_manager.create_from_signal(s1, quantity=5)
        o2 = order_manager.create_from_signal(s2, quantity=3)
        order_manager.mark_submitted(o1.client_order_id, "b1")
        order_manager.mark_submitted(o2.client_order_id, "b2")
        order_manager.mark_filled(o2.client_order_id, 3.0, 100.0)
        active = order_manager.active_orders()
        assert len(active) == 1
        assert active[0].symbol == "AAPL"

    def test_sell_signal_creates_sell_order(self, order_manager):
        sell_signal = Signal(symbol="NVDA", action=SignalAction.SELL)
        order = order_manager.create_from_signal(sell_signal, quantity=2)
        assert order.side == OrderSide.SELL

    def test_sell_short_signal(self, order_manager):
        short_signal = Signal(symbol="TSLA", action=SignalAction.SELL_SHORT)
        order = order_manager.create_from_signal(short_signal, quantity=1)
        assert order.side == OrderSide.SELL_SHORT

    def test_order_is_active_property(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        assert order.is_active is True  # NEW is active

    def test_order_is_terminal_after_fill(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        order_manager.mark_submitted(order.client_order_id, "b-1")
        order_manager.mark_filled(order.client_order_id, 5.0, 200.0)
        assert order.is_terminal is True


# ══════════════════════════════════════════════════════════════════════════════
# ExecutionEngine Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestExecutionEngine:

    def test_submit_success(self, engine, buy_order, mock_broker):
        response = engine.submit(buy_order)
        assert response["order_id"] == "broker-001"
        mock_broker.place_order.assert_called_once()

    def test_submit_updates_order_to_submitted(self, engine, buy_order):
        engine.submit(buy_order)
        assert buy_order.status == OrderState.SUBMITTED
        assert buy_order.broker_order_id == "broker-001"

    def test_submit_increments_count(self, engine, buy_order):
        engine.submit(buy_order)
        assert engine.stats["submission_count"] == 1

    def test_kill_switch_blocks_submission(self, engine, buy_order, kill_switch):
        kill_switch.activate(KillSwitchReason.DAILY_LOSS_LIMIT)
        with pytest.raises(KillSwitchError):
            engine.submit(buy_order)

    def test_kill_switch_does_not_submit_to_broker(self, engine, buy_order, kill_switch, mock_broker):
        kill_switch.activate(KillSwitchReason.OPERATOR)
        with pytest.raises(KillSwitchError):
            engine.submit(buy_order)
        mock_broker.place_order.assert_not_called()

    def test_invalid_quantity_raises(self, engine, order_manager):
        order = order_manager.create(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=0,
        )
        with pytest.raises(ValueError, match="invalid quantity"):
            engine.submit(order)

    def test_empty_symbol_raises(self, engine, order_manager):
        order = order_manager.create(
            symbol="   ",
            side=OrderSide.BUY,
            quantity=5,
        )
        with pytest.raises(ValueError, match="empty symbol"):
            engine.submit(order)

    def test_non_new_order_raises(self, engine, buy_order, order_manager):
        order_manager.mark_submitted(buy_order.client_order_id, "b-prev")
        with pytest.raises(ExecutionError):
            engine.submit(buy_order)  # Already SUBMITTED

    def test_broker_rejection_marks_order_rejected(self, engine, buy_order, mock_broker):
        mock_broker.place_order.side_effect = OrderRejectedError("Insufficient funds")
        with pytest.raises(OrderRejectedError):
            engine.submit(buy_order)
        assert buy_order.status == OrderState.REJECTED

    def test_dry_run_does_not_call_broker(self, mock_broker, order_manager, kill_switch, buy_signal):
        dry_engine = ExecutionEngine(
            broker=mock_broker,
            order_manager=order_manager,
            kill_switch=kill_switch,
            account_id="TEST",
            dry_run=True,
        )
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        response = dry_engine.submit(order)
        mock_broker.place_order.assert_not_called()
        assert response["status"] == "DRY_RUN"
        assert order.status == OrderState.SUBMITTED

    def test_stats_failure_count_on_rejection(self, engine, buy_order, mock_broker):
        mock_broker.place_order.side_effect = OrderRejectedError("Bad symbol")
        with pytest.raises(OrderRejectedError):
            engine.submit(buy_order)
        assert engine.stats["failure_count"] == 1

    def test_limit_order_without_price_raises(self, engine, order_manager):
        order = order_manager.create(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=5,
            order_type=OrderType.LIMIT,
            limit_price=None,
        )
        with pytest.raises(ValueError, match="limit_price"):
            engine.submit(order)


# ══════════════════════════════════════════════════════════════════════════════
# OrderReconciler Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderReconciler:

    @pytest.fixture
    def unknown_order(self, order_manager, buy_signal):
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        order_manager.mark_submitted(order.client_order_id, "broker-rec-001")
        order_manager.mark_unknown(order.client_order_id, "network error")
        return order

    def test_reconcile_resolves_filled(self, order_manager, mock_broker, unknown_order):
        mock_broker.get_order_status.return_value = {
            "order_id": "broker-rec-001",
            "status": "filled",
            "filled_quantity": 5.0,
            "avg_fill_price": 175.0,
        }
        reconciler = OrderReconciler(order_manager, mock_broker, "TEST")
        result = reconciler.reconcile_order(unknown_order.client_order_id)
        assert result is True
        assert unknown_order.status == OrderState.FILLED
        assert unknown_order.filled_quantity == 5.0

    def test_reconcile_resolves_cancelled(self, order_manager, mock_broker, unknown_order):
        mock_broker.get_order_status.return_value = {
            "order_id": "broker-rec-001",
            "status": "canceled",
            "filled_quantity": 0.0,
            "avg_fill_price": 0.0,
        }
        reconciler = OrderReconciler(order_manager, mock_broker, "TEST")
        reconciler.reconcile_order(unknown_order.client_order_id)
        assert unknown_order.status == OrderState.CANCELLED

    def test_reconcile_unknown_only_processes_unknown_orders(self, order_manager, mock_broker, buy_signal):
        # Create a filled order (terminal, not UNKNOWN)
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        order_manager.mark_submitted(order.client_order_id, "b-filled")
        order_manager.mark_filled(order.client_order_id, 5.0, 100.0)

        reconciler = OrderReconciler(order_manager, mock_broker, "TEST")
        count = reconciler.reconcile_unknown()
        assert count == 0
        mock_broker.get_order_status.assert_not_called()

    def test_reconcile_order_without_broker_id_raises(self, order_manager, mock_broker, buy_signal):
        from pyrobot.exceptions import ReconciliationError
        order = order_manager.create_from_signal(buy_signal, quantity=5)
        # Manually set to UNKNOWN without a broker_order_id
        order.status = OrderState.UNKNOWN
        reconciler = OrderReconciler(order_manager, mock_broker, "TEST")
        with pytest.raises(ReconciliationError):
            reconciler.reconcile_order(order.client_order_id)
