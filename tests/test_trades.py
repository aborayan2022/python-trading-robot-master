"""Tests for the Trade class."""


from pyrobot.trades import Trade


class TestTrade:
    """Tests for Trade object creation and manipulation."""

    def test_new_trade_market(self):
        trade = Trade()
        order = trade.new_trade(
            trade_id="test_1",
            order_type="mkt",
            side="long",
            enter_or_exit="enter",
        )
        assert order["orderType"] == "MARKET"
        assert order["orderLegCollection"][0]["instruction"] == "BUY"

    def test_new_trade_limit(self):
        trade = Trade()
        order = trade.new_trade(
            trade_id="test_2",
            order_type="lmt",
            side="long",
            enter_or_exit="enter",
            price=150.00,
        )
        assert order["orderType"] == "LIMIT"
        assert order["price"] == 150.00

    def test_new_trade_stop(self):
        trade = Trade()
        order = trade.new_trade(
            trade_id="test_3",
            order_type="stop",
            side="long",
            enter_or_exit="enter",
            price=140.00,
        )
        assert order["orderType"] == "STOP"
        assert order["stopPrice"] == 140.00

    def test_instrument(self):
        trade = Trade()
        trade.new_trade(
            trade_id="test_4",
            order_type="mkt",
            side="long",
            enter_or_exit="enter",
        )
        leg = trade.instrument(symbol="MSFT", quantity=10, asset_type="EQUITY")
        assert leg["instrument"]["symbol"] == "MSFT"
        assert leg["quantity"] == 10

    def test_add_leg_fix(self):
        trade = Trade()
        trade.new_trade(
            trade_id="test_5",
            order_type="mkt",
            side="long",
            enter_or_exit="enter",
        )
        trade.instrument(symbol="MSFT", quantity=10, asset_type="EQUITY")
        legs = trade.add_leg(
            order_leg_id=1, symbol="AAPL", quantity=5, asset_type="EQUITY"
        )
        assert len(legs) == 2
        assert legs[1]["instrument"]["symbol"] == "AAPL"

    def test_repr(self):
        trade = Trade()
        trade.new_trade(
            trade_id="test_6",
            order_type="mkt",
            side="long",
            enter_or_exit="enter",
        )
        trade.instrument(symbol="MSFT", quantity=10, asset_type="EQUITY")
        r = repr(trade)
        assert "MSFT" in r
        assert "long" in r

    def test_generate_order_id(self):
        trade = Trade()
        trade.new_trade(
            trade_id="test_7",
            order_type="mkt",
            side="long",
            enter_or_exit="enter",
        )
        trade.instrument(symbol="MSFT", quantity=10, asset_type="EQUITY")
        order_id = trade._generate_order_id()
        assert "MSFT" in order_id
        assert "long" in order_id

    def test_convert_to_trigger(self):
        trade = Trade()
        trade.new_trade(
            trade_id="test_8",
            order_type="mkt",
            side="long",
            enter_or_exit="enter",
        )
        trade.instrument(symbol="MSFT", quantity=10, asset_type="EQUITY")
        trade._convert_to_trigger()
        assert trade._triggered_added is True
        assert trade.order["orderStrategyType"] == "TRIGGER"
        assert "childOrderStrategies" in trade.order

    def test_stop_loss_order_type(self):
        trade = Trade()
        trade.new_trade(
            trade_id="test_9",
            order_type="stop",
            side="long",
            enter_or_exit="enter",
            price=140.0,
        )
        assert trade.is_stop_order is True
        assert trade.is_limit_order is False

    def test_limit_order_type(self):
        trade = Trade()
        trade.new_trade(
            trade_id="test_10",
            order_type="lmt",
            side="long",
            enter_or_exit="enter",
            price=150.0,
        )
        assert trade.is_limit_order is True
        assert trade.is_stop_order is False
