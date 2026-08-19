"""Tests for canonical domain models."""

import pytest

from datetime import datetime, timezone
from pyrobot.models import Order, OrderState, OrderSide, OrderType, TimeInForce
from pyrobot.models import Position, PositionSide
from pyrobot.models import Signal, SignalAction


class TestOrderState:
    """Tests for OrderState enum."""

    def test_all_states_exist(self):
        assert OrderState.NEW.value == "NEW"
        assert OrderState.SUBMITTED.value == "SUBMITTED"
        assert OrderState.ACKNOWLEDGED.value == "ACKNOWLEDGED"
        assert OrderState.PARTIALLY_FILLED.value == "PARTIALLY_FILLED"
        assert OrderState.FILLED.value == "FILLED"
        assert OrderState.CANCEL_PENDING.value == "CANCEL_PENDING"
        assert OrderState.CANCELLED.value == "CANCELLED"
        assert OrderState.REJECTED.value == "REJECTED"
        assert OrderState.EXPIRED.value == "EXPIRED"
        assert OrderState.UNKNOWN.value == "UNKNOWN"

    def test_states_count(self):
        assert len(OrderState) == 10


class TestOrderSide:
    """Tests for OrderSide enum."""

    def test_sides(self):
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"
        assert OrderSide.SELL_SHORT.value == "SELL_SHORT"
        assert OrderSide.BUY_TO_COVER.value == "BUY_TO_COVER"


class TestOrder:
    """Tests for Order model."""

    def test_create_market_order(self):
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
        )
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity == 100
        assert order.order_type == OrderType.MARKET
        assert order.status == OrderState.NEW
        assert order.client_order_id is not None
        assert order.timestamp is not None
        assert order.timestamp.tzinfo == timezone.utc

    def test_create_limit_order(self):
        order = Order(
            symbol="MSFT",
            side=OrderSide.SELL,
            quantity=50,
            order_type=OrderType.LIMIT,
            limit_price=420.0,
        )
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 420.0

    def test_create_stop_order(self):
        order = Order(
            symbol="TSLA",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.STOP,
            stop_price=250.0,
        )
        assert order.order_type == OrderType.STOP
        assert order.stop_price == 250.0

    def test_is_active_new(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        assert order.is_active is True

    def test_is_active_submitted(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        order.status = OrderState.SUBMITTED
        assert order.is_active is True

    def test_is_active_filled(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        order.status = OrderState.FILLED
        assert order.is_active is False

    def test_is_terminal_filled(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        order.status = OrderState.FILLED
        assert order.is_terminal is True

    def test_is_terminal_cancelled(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        order.status = OrderState.CANCELLED
        assert order.is_terminal is True

    def test_is_terminal_new(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        assert order.is_terminal is False

    def test_remaining_quantity(self):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=100)
        order.filled_quantity = 30
        assert order.remaining_quantity == 70

    def test_to_legacy_dict(self):
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
        )
        legacy = order.to_legacy_dict()

        assert legacy["symbol"] == "AAPL"
        assert legacy["orderType"] == "MARKET"
        assert len(legacy["orderLegCollection"]) == 1
        assert legacy["orderLegCollection"][0]["instruction"] == "BUY"
        assert legacy["orderLegCollection"][0]["quantity"] == 100
        assert legacy["orderLegCollection"][0]["instrument"]["symbol"] == "AAPL"

    def test_to_legacy_dict_with_limit(self):
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=150.0,
        )
        legacy = order.to_legacy_dict()
        assert legacy["price"] == 150.0

    def test_from_legacy_dict(self):
        legacy = {
            "orderType": "MARKET",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": 50,
                    "instrument": {
                        "symbol": "MSFT",
                        "assetType": "EQUITY",
                    },
                }
            ],
        }
        order = Order.from_legacy_dict(legacy)

        assert order.symbol == "MSFT"
        assert order.side == OrderSide.BUY
        assert order.quantity == 50
        assert order.order_type == OrderType.MARKET

    def test_from_legacy_dict_flat_format(self):
        legacy = {
            "symbol": "GOOG",
            "orderType": "LIMIT",
            "price": 2800.0,
        }
        order = Order.from_legacy_dict(legacy)

        assert order.symbol == "GOOG"
        assert order.limit_price == 2800.0

    def test_to_dict(self):
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
        )
        d = order.to_dict()

        assert d["symbol"] == "AAPL"
        assert d["side"] == "BUY"
        assert d["quantity"] == 100
        assert "client_order_id" in d
        assert "timestamp" in d

    def test_unique_client_order_id(self):
        order1 = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        order2 = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        assert order1.client_order_id != order2.client_order_id


class TestPosition:
    """Tests for Position model."""

    def test_create_position(self):
        pos = Position(symbol="AAPL", quantity=100, avg_entry_price=150.0)
        assert pos.symbol == "AAPL"
        assert pos.quantity == 100
        assert pos.avg_entry_price == 150.0
        assert pos.side == PositionSide.FLAT

    def test_long_position(self):
        pos = Position(symbol="AAPL", side=PositionSide.LONG, quantity=100)
        assert pos.is_long is True
        assert pos.is_short is False

    def test_short_position(self):
        pos = Position(symbol="TSLA", side=PositionSide.SHORT, quantity=-10)
        assert pos.is_short is True
        assert pos.is_long is False

    def test_is_open(self):
        pos = Position(symbol="AAPL", quantity=100)
        assert pos.is_open is True

    def test_is_not_open(self):
        pos = Position(symbol="AAPL", quantity=0)
        assert pos.is_open is False

    def test_update_market_value(self):
        pos = Position(symbol="AAPL", side=PositionSide.LONG, quantity=100, avg_entry_price=150.0)
        pos.update_market_value(160.0)

        assert pos.current_price == 160.0
        assert pos.market_value == 16000.0
        assert pos.unrealized_pnl == 1000.0

    def test_update_market_value_short(self):
        pos = Position(symbol="TSLA", side=PositionSide.SHORT, quantity=-10, avg_entry_price=250.0)
        pos.update_market_value(240.0)

        assert pos.unrealized_pnl == 100.0  # Short profits when price drops

    def test_to_dict(self):
        pos = Position(symbol="AAPL", quantity=100, avg_entry_price=150.0)
        d = pos.to_dict()

        assert d["symbol"] == "AAPL"
        assert d["quantity"] == 100
        assert d["avg_entry_price"] == 150.0

    def test_from_broker_dict(self):
        broker_dict = {
            "symbol": "AAPL",
            "quantity": 100,
            "average_price": 150.0,
            "market_value": 16000.0,
            "asset_type": "EQUITY",
        }
        pos = Position.from_broker_dict(broker_dict)

        assert pos.symbol == "AAPL"
        assert pos.quantity == 100
        assert pos.avg_entry_price == 150.0


class TestSignalAction:
    """Tests for SignalAction enum."""

    def test_actions(self):
        assert SignalAction.BUY.value == "BUY"
        assert SignalAction.SELL.value == "SELL"
        assert SignalAction.HOLD.value == "HOLD"
        assert SignalAction.NO_TRADE.value == "NO_TRADE"


class TestSignal:
    """Tests for Signal model."""

    def test_create_signal(self):
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.BUY,
            probability=0.75,
            confidence=0.8,
        )
        assert signal.symbol == "AAPL"
        assert signal.action == SignalAction.BUY
        assert signal.probability == 0.75
        assert signal.confidence == 0.8
        assert signal.timestamp.tzinfo == timezone.utc
        assert signal.signal_id is not None

    def test_is_actionable_buy(self):
        signal = Signal(symbol="AAPL", action=SignalAction.BUY)
        assert signal.is_actionable is True

    def test_is_actionable_sell(self):
        signal = Signal(symbol="AAPL", action=SignalAction.SELL)
        assert signal.is_actionable is True

    def test_is_not_actionable_hold(self):
        signal = Signal(symbol="AAPL", action=SignalAction.HOLD)
        assert signal.is_actionable is False

    def test_is_not_actionable_no_trade(self):
        signal = Signal(symbol="AAPL", action=SignalAction.NO_TRADE)
        assert signal.is_actionable is False

    def test_risk_reward_ratio(self):
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.BUY,
            expected_return=0.15,
            expected_risk=0.05,
        )
        assert signal.risk_reward_ratio == pytest.approx(3.0)

    def test_risk_reward_ratio_none(self):
        signal = Signal(symbol="AAPL", action=SignalAction.BUY)
        assert signal.risk_reward_ratio is None

    def test_from_legacy_action_buy(self):
        signal = Signal.from_legacy_action("AAPL", "buy")
        assert signal.action == SignalAction.BUY

    def test_from_legacy_action_sell(self):
        signal = Signal.from_legacy_action("AAPL", "sell")
        assert signal.action == SignalAction.SELL

    def test_from_legacy_action_none(self):
        signal = Signal.from_legacy_action("AAPL", None)
        assert signal.action == SignalAction.NO_TRADE

    def test_to_dict(self):
        signal = Signal(
            symbol="AAPL",
            action=SignalAction.BUY,
            probability=0.75,
        )
        d = signal.to_dict()

        assert d["symbol"] == "AAPL"
        assert d["action"] == "BUY"
        assert d["probability"] == 0.75
        assert "signal_id" in d
        assert "timestamp" in d
