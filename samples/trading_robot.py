"""
Trading Robot Example — Uses the broker abstraction layer.

Supports: paper, schwab, alpaca, ibkr
Install broker extras: pip install python-trading-robot[alpaca]
"""

import time as time_lib
import pprint
import operator
from datetime import datetime, timedelta

from pyrobot.robot import PyRobot
from pyrobot.indicators import Indicators
from pyrobot.brokers import create_broker

# --- Choose your broker ---
# For live trading, replace 'paper' with 'schwab', 'alpaca', or 'ibkr'
# and provide the required credentials.

broker = create_broker('paper')  # Local simulator, no credentials needed
broker.authenticate()

# Initialize the robot.
trading_robot = PyRobot(broker=broker)

# Create a Portfolio.
trading_robot_portfolio = trading_robot.create_portfolio()

# Define multiple positions to add.
multi_position = [
    {
        'asset_type': 'equity',
        'quantity': 2,
        'purchase_price': 250.00,
        'symbol': 'MSFT',
        'purchase_date': '2024-01-15'
    },
    {
        'asset_type': 'equity',
        'quantity': 3,
        'purchase_price': 180.00,
        'symbol': 'AAPL',
        'purchase_date': '2024-01-15'
    }
]

# Grab the New positions.
new_positions = trading_robot.portfolio.add_positions(positions=multi_position)
pprint.pprint(new_positions)

# Add a single position.
trading_robot_portfolio.add_position(
    symbol='GOOGL',
    quantity=5,
    purchase_price=140.00,
    asset_type='equity',
    purchase_date='2024-02-01'
)

# Print the Positions.
pprint.pprint(trading_robot_portfolio.positions)

# Print the Portfolio summary.
print("\n=== Portfolio Summary ===")
pprint.pprint(trading_robot_portfolio.projected_market_value(
    current_prices=trading_robot.grab_current_quotes()
))

# Create a new Trade Object.
new_trade = trading_robot.create_trade(
    trade_id='long_msft',
    enter_or_exit='enter',
    long_or_short='long',
    order_type='mkt'
)

# Add an Instrument.
new_trade.instrument(
    symbol='MSFT',
    quantity=5,
    asset_type='EQUITY'
)

# Print out the order.
pprint.pprint(new_trade.order)

print("\n=== Example complete! ===")
print("For live trading, replace create_broker('paper') with:")
print("  broker = create_broker('schwab', client_id='...', redirect_uri='...')")
print("  broker = create_broker('alpaca', api_key='...', secret_key='...')")
