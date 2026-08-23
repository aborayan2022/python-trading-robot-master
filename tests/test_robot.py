"""Tests for the PyRobot class."""

import pandas as pd

from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.robot import PyRobot


class SpyPaperBroker(PaperBroker):
    """PaperBroker spy that counts broker.place_order calls."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.place_order_calls = 0

    def place_order(self, account: str, order: dict) -> dict:
        self.place_order_calls += 1
        return super().place_order(account, order)


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

    def test_execute_signals_routes_through_broker(self, monkeypatch):
        """Paper mode must call broker.place_order, not fabricate order ids."""
        broker = SpyPaperBroker()
        broker.authenticate()
        broker.update_prices({"MSFT": {"close": 400.0}})
        robot = PyRobot(broker=broker, paper_trading=True)
        robot.create_portfolio()
        monkeypatch.setattr(robot, "save_orders", lambda order_response_dict: True)

        trade = robot.create_trade(
            trade_id="long_msft",
            enter_or_exit="enter",
            long_or_short="long",
            order_type="mkt",
        )
        trade.instrument(symbol="MSFT", quantity=10, asset_type="EQUITY")
        trades_to_execute = {
            "MSFT": {
                "has_executed": False,
                "buy": {"trade_func": trade},
                "sell": {"trade_func": trade},
            }
        }
        signals = {
            "buys": pd.Series(
                [1.0],
                index=pd.MultiIndex.from_tuples(
                    [("MSFT", pd.Timestamp("2024-01-02 14:30"))]
                ),
            ),
            "sells": pd.Series(),
        }

        responses = robot.execute_signals(
            signals=signals, trades_to_execute=trades_to_execute
        )

        assert broker.place_order_calls == 1
        assert len(responses) == 1
        # The order id must come from the broker, not be fabricated.
        assert responses[0]["order_id"] == broker.order_history[0]["order_id"]
        assert responses[0]["status"] == "FILLED"
        assert trades_to_execute["MSFT"]["has_executed"] is True

    def test_execute_signals_routes_sells_through_broker(self, monkeypatch):
        """Sell signals must also be routed through the broker."""
        broker = SpyPaperBroker()
        broker.authenticate()
        broker.update_prices({"MSFT": {"close": 400.0}})
        robot = PyRobot(broker=broker, paper_trading=True)
        robot.create_portfolio()
        monkeypatch.setattr(robot, "save_orders", lambda order_response_dict: True)

        trade = robot.create_trade(
            trade_id="short_msft",
            enter_or_exit="enter",
            long_or_short="short",
            order_type="mkt",
        )
        trade.instrument(symbol="MSFT", quantity=10, asset_type="EQUITY")
        trades_to_execute = {
            "MSFT": {
                "has_executed": False,
                "buy": {"trade_func": trade},
                "sell": {"trade_func": trade},
            }
        }
        signals = {
            "buys": pd.Series(),
            "sells": pd.Series(
                [1.0],
                index=pd.MultiIndex.from_tuples(
                    [("MSFT", pd.Timestamp("2024-01-02 14:30"))]
                ),
            ),
        }

        responses = robot.execute_signals(
            signals=signals, trades_to_execute=trades_to_execute
        )

        assert broker.place_order_calls == 1
        assert len(responses) == 1
        assert responses[0]["order_id"] == broker.order_history[0]["order_id"]
