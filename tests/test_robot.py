"""Tests for the PyRobot class."""

import pytest

from pyrobot.robot import PyRobot
from pyrobot.brokers.paper_broker import PaperBroker


class TestPyRobot:
    """Tests for PyRobot with PaperBroker."""

    def test_creates_instance_with_broker(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        assert robot.broker is not None
        assert robot.broker.name == "paper"

    def test_creates_instance_default_broker(self):
        robot = PyRobot()
        assert robot.broker is not None
        assert isinstance(robot.broker, PaperBroker)

    def test_create_portfolio(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        portfolio = robot.create_portfolio()
        assert portfolio is not None
        assert portfolio.broker is not None

    def test_create_trade(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        robot.create_portfolio()
        trade = robot.create_trade(
            trade_id="long_msft",
            enter_or_exit="enter",
            long_or_short="long",
            order_type="mkt",
        )
        assert trade is not None
        assert "long_msft" in robot.trades
        assert trade.order["orderLegCollection"][0]["instruction"] == "BUY"

    def test_delete_trade(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        robot.create_portfolio()
        robot.create_trade(
            trade_id="long_msft",
            enter_or_exit="enter",
            long_or_short="long",
            order_type="mkt",
        )
        robot.delete_trade("long_msft")
        assert "long_msft" not in robot.trades

    def test_grab_current_quotes(self):
        broker = PaperBroker()
        broker.authenticate()
        broker.update_prices(
            {"MSFT": {"close": 400.0, "last_price": 400.0}}
        )
        robot = PyRobot(broker=broker)
        robot.create_portfolio()
        robot.portfolio.add_position(
            symbol="MSFT", asset_type="equity", quantity=10
        )
        quotes = robot.grab_current_quotes()
        assert "MSFT" in quotes

    def test_create_stock_frame(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        data = [
            {
                "symbol": "MSFT",
                "open": 400.0,
                "close": 401.0,
                "high": 402.0,
                "low": 399.0,
                "volume": 50000,
                "datetime": 1704219000000,
            }
        ]
        stock_frame = robot.create_stock_frame(data=data)
        assert stock_frame is not None
        assert robot.stock_frame is stock_frame

    def test_market_hours_properties(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        # These should return booleans without error
        assert isinstance(robot.pre_market_open, bool)
        assert isinstance(robot.post_market_open, bool)
        assert isinstance(robot.regular_market_open, bool)

    def test_execute_signals_empty(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        robot.create_portfolio()
        signals = {"buys": __import__("pandas").Series(), "sells": __import__("pandas").Series()}
        result = robot.execute_signals(signals=signals, trades_to_execute={})
        assert result == []

    def test_get_positions(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker)
        robot.create_portfolio()
        positions = robot.get_positions()
        assert isinstance(positions, list)

    def test_get_accounts(self):
        broker = PaperBroker()
        broker.authenticate()
        robot = PyRobot(broker=broker, trading_account="TEST")
        robot.create_portfolio()
        accounts = robot.get_accounts()
        assert isinstance(accounts, dict)
        assert "cash_balance" in accounts
