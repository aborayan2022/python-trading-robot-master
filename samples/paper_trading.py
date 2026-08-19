"""Sample: Trading robot using the PaperBroker for local simulation."""

import operator
import pprint

from datetime import datetime
from datetime import timedelta

from pyrobot.robot import PyRobot
from pyrobot.indicators import Indicators
from pyrobot.brokers import PaperBroker

# Create a PaperBroker with $100k starting balance.
broker = PaperBroker(initial_balance=100_000.0)
broker.authenticate()

# Initialize the robot with the broker.
trading_robot = PyRobot(broker=broker, paper_trading=True)

# Create a Portfolio.
trading_robot_portfolio = trading_robot.create_portfolio()

# Add positions.
multi_position = [
    {
        "asset_type": "equity",
        "quantity": 10,
        "purchase_price": 400.00,
        "symbol": "MSFT",
        "purchase_date": "2024-01-01",
    },
    {
        "asset_type": "equity",
        "quantity": 5,
        "purchase_price": 180.00,
        "symbol": "AAPL",
        "purchase_date": "2024-01-01",
    },
]

new_positions = trading_robot.portfolio.add_positions(positions=multi_position)
pprint.pprint(new_positions)

# Simulate some price updates for the paper broker.
broker.update_prices(
    {
        "MSFT": {"close": 420.0, "open": 418.0, "high": 422.0, "low": 417.0, "volume": 50000},
        "AAPL": {"close": 185.0, "open": 183.0, "high": 186.0, "low": 182.0, "volume": 30000},
    }
)

# Get quotes.
quotes = trading_robot.grab_current_quotes()
pprint.pprint(quotes)

# Check profitability.
is_profitable = trading_robot.portfolio.is_profitable(
    symbol="MSFT", current_price=quotes["MSFT"]["last_price"]
)
print(f"Is MSFT profitable: {is_profitable}")

# Create a trade.
new_trade = trading_robot.create_trade(
    trade_id="long_msft",
    enter_or_exit="enter",
    long_or_short="long",
    order_type="mkt",
)
new_trade.instrument(symbol="MSFT", quantity=5, asset_type="EQUITY")

print(f"Trade: {new_trade}")
print(f"Order: {new_trade.order}")

# Portfolio summary.
positions = trading_robot.get_positions()
pprint.pprint(positions)
