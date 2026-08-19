import json
import time as time_true
import pathlib
import warnings

import pandas as pd

from datetime import datetime
from datetime import timezone
from datetime import timedelta

from typing import List
from typing import Dict
from typing import Union
from typing import Optional

from pyrobot.trades import Trade
from pyrobot.portfolio import Portfolio
from pyrobot.stock_frame import StockFrame
from pyrobot.brokers.base import BrokerInterface
from pyrobot.logging_config import get_logger

logger = get_logger("robot")


class PyRobot():

    def __init__(
        self,
        client_id: str = None,
        redirect_uri: str = None,
        paper_trading: bool = True,
        credentials_path: str = None,
        trading_account: str = None,
        broker: BrokerInterface = None,
    ) -> None:
        """Initalizes a new instance of the robot.

        Arguments:
        ----
        broker {BrokerInterface} -- A broker adapter instance (preferred).

        Legacy arguments (deprecated, will be removed in v1.0):
            client_id {str} -- The Consumer ID assigned to you during the App registration.
            redirect_uri {str} -- This is the redirect URL that you specified when you created your
                TD Ameritrade Application.
            credentials_path {str} -- The path to the session state file.
            trading_account {str} -- Your trading account number.
        """

        self.trading_account = trading_account
        self.trades = {}
        self.historical_prices = {}
        self.stock_frame: StockFrame = None
        self.paper_trading = paper_trading

        self._bar_size = None
        self._bar_type = None

        if broker is not None:
            self.broker = broker
            self.broker.authenticate()
        elif client_id is not None:
            warnings.warn(
                "Direct client_id/redirect_uri constructor is deprecated. "
                "Use PyRobot(broker=YourBroker(...)) instead. "
                "This will be removed in v1.0.",
                DeprecationWarning,
                stacklevel=2,
            )
            self.broker = self._create_legacy_session(
                client_id, redirect_uri, credentials_path
            )
        else:
            from pyrobot.brokers import PaperBroker

            self.broker = PaperBroker()
            self.broker.authenticate()
            logger.info("No broker provided, defaulting to PaperBroker")

    def _create_legacy_session(self, client_id, redirect_uri, credentials_path):
        """Create a legacy TD Ameritrade session (deprecated)."""
        try:
            from td.client import TDClient
            from td.utils import TDUtilities

            self._milliseconds_since_epoch = TDUtilities().milliseconds_since_epoch

            td_client = TDClient(
                client_id=client_id,
                redirect_uri=redirect_uri,
                credentials_path=credentials_path,
            )
            td_client.login()
            return td_client
        except ImportError:
            raise ImportError(
                "The td-ameritrade-python-api package is required for legacy mode. "
                "Install it with: pip install td-ameritrade-python-api"
            )

    @property
    def pre_market_open(self) -> bool:
        """Checks if pre-market is open (8:00 - 13:30 UTC)."""
        pre_market_start_time = datetime.now(timezone.utc).replace(
            hour=8, minute=0, second=0
        ).timestamp()

        market_start_time = datetime.now(timezone.utc).replace(
            hour=13, minute=30, second=0
        ).timestamp()

        right_now = datetime.now(timezone.utc).timestamp()

        return market_start_time >= right_now >= pre_market_start_time

    @property
    def post_market_open(self):
        """Checks if post-market is open (20:00 - 00:00 UTC)."""
        post_market_end_time = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0
        ).timestamp()

        market_end_time = datetime.now(timezone.utc).replace(
            hour=20, minute=0, second=0
        ).timestamp()

        right_now = datetime.now(timezone.utc).timestamp()

        return post_market_end_time >= right_now >= market_end_time

    @property
    def regular_market_open(self):
        """Checks if regular market is open (13:30 - 20:00 UTC)."""
        market_start_time = datetime.now(timezone.utc).replace(
            hour=13, minute=30, second=0
        ).timestamp()

        market_end_time = datetime.now(timezone.utc).replace(
            hour=20, minute=0, second=0
        ).timestamp()

        right_now = datetime.now(timezone.utc).timestamp()

        return market_end_time >= right_now >= market_start_time

    def create_portfolio(self) -> Portfolio:
        """Create a new portfolio."""
        self.portfolio = Portfolio(account_number=self.trading_account)
        self.portfolio.broker = self.broker
        return self.portfolio

    def create_trade(
        self,
        trade_id: str,
        enter_or_exit: str,
        long_or_short: str,
        order_type: str = "mkt",
        price: float = 0.0,
        stop_limit_price=0.0,
    ) -> Trade:
        """Initalizes a new instance of a Trade Object."""
        trade = Trade()
        trade.new_trade(
            trade_id=trade_id,
            order_type=order_type,
            side=long_or_short,
            enter_or_exit=enter_or_exit,
            price=price,
            stop_limit_price=stop_limit_price,
        )
        trade.account = self.trading_account
        trade._broker = self.broker

        self.trades[trade_id] = trade
        return trade

    def delete_trade(self, index: int) -> None:
        """Deletes an exisiting trade from the `trades` collection."""
        if index in self.trades:
            del self.trades[index]

    def grab_current_quotes(self) -> dict:
        """Grabs the current quotes for all positions in the portfolio."""
        symbols = list(self.portfolio.positions.keys())
        return self.broker.get_quotes(symbols=symbols)

    def grab_historical_prices(
        self,
        start: datetime,
        end: datetime,
        bar_size: int = 1,
        bar_type: str = "minute",
        symbols: List[str] = None,
    ) -> List[dict]:
        """Grabs the historical prices for all the postions in a portfolio."""
        self._bar_size = bar_size
        self._bar_type = bar_type

        new_prices = []

        if not symbols:
            symbols = list(self.portfolio.positions.keys())

        for symbol in symbols:
            candles = self.broker.get_historical_prices(
                symbol=symbol,
                start=start,
                end=end,
                bar_size=bar_size,
                bar_type=bar_type,
            )
            self.historical_prices[symbol] = {"candles": candles}
            new_prices.extend(candles)

        self.historical_prices["aggregated"] = new_prices
        return self.historical_prices

    def get_latest_bar(self) -> List[dict]:
        """Returns the latest bar for each symbol in the portfolio."""
        bar_size = self._bar_size
        bar_type = self._bar_type

        end_date = datetime.today()
        start_date = end_date - timedelta(days=1)

        latest_prices = []

        for symbol in self.portfolio.positions:
            try:
                candles = self.broker.get_historical_prices(
                    symbol=symbol,
                    start=start_date,
                    end=end_date,
                    bar_size=bar_size,
                    bar_type=bar_type,
                )
                if candles:
                    latest_prices.append(candles[-1])
            except Exception as e:
                logger.warning(f"Failed to get latest bar for {symbol}: {e}")
                time_true.sleep(2)

        return latest_prices

    def wait_till_next_bar(self, last_bar_timestamp: pd.DatetimeIndex) -> None:
        """Waits the number of seconds till the next bar is released."""
        last_bar_time = last_bar_timestamp.to_pydatetime()[0].replace(
            tzinfo=timezone.utc
        )
        next_bar_time = last_bar_time + timedelta(seconds=60)
        curr_bar_time = datetime.now(tz=timezone.utc)

        next_bar_timestamp = int(next_bar_time.timestamp())
        curr_bar_timestamp = int(curr_bar_time.timestamp())

        time_to_wait_now = next_bar_timestamp - curr_bar_timestamp

        if time_to_wait_now < 0:
            time_to_wait_now = 0

        logger.info(
            f"Pausing {time_to_wait_now}s until next bar "
            f"(current: {curr_bar_time.strftime('%H:%M:%S')}, "
            f"next: {next_bar_time.strftime('%H:%M:%S')})"
        )

        time_true.sleep(time_to_wait_now)

    def create_stock_frame(self, data: List[dict]) -> StockFrame:
        """Generates a new StockFrame Object."""
        self.stock_frame = StockFrame(data=data)
        return self.stock_frame

    def execute_signals(
        self, signals: List[pd.Series], trades_to_execute: dict
    ) -> List[dict]:
        """Executes the specified trades for each signal."""
        buys: pd.Series = signals.get("buys", pd.Series())
        sells: pd.Series = signals.get("sells", pd.Series())

        order_responses = []

        if not buys.empty:
            symbols_list = buys.index.get_level_values(0).to_list()
            for symbol in symbols_list:
                if symbol in trades_to_execute:
                    if self.portfolio.in_portfolio(symbol=symbol):
                        self.portfolio.set_ownership_status(
                            symbol=symbol, ownership=True
                        )
                    trades_to_execute[symbol]["has_executed"] = True
                    trade_obj: Trade = trades_to_execute[symbol]["buy"]["trade_func"]

                    if not self.paper_trading:
                        order_response = self.execute_orders(trade_obj=trade_obj)
                        order_response = {
                            "order_id": order_response["order_id"],
                            "request_body": order_response["request_body"],
                            "timestamp": datetime.now().isoformat(),
                        }
                    else:
                        order_response = {
                            "order_id": trade_obj._generate_order_id(),
                            "request_body": trade_obj.order,
                            "timestamp": datetime.now().isoformat(),
                        }
                    order_responses.append(order_response)

        if not sells.empty:
            symbols_list = sells.index.get_level_values(0).to_list()
            for symbol in symbols_list:
                if symbol in trades_to_execute:
                    trades_to_execute[symbol]["has_executed"] = True
                    if self.portfolio.in_portfolio(symbol=symbol):
                        self.portfolio.set_ownership_status(
                            symbol=symbol, ownership=False
                        )
                    trade_obj: Trade = trades_to_execute[symbol]["sell"]["trade_func"]

                    if not self.paper_trading:
                        order_response = self.execute_orders(trade_obj=trade_obj)
                        order_response = {
                            "order_id": order_response["order_id"],
                            "request_body": order_response["request_body"],
                            "timestamp": datetime.now().isoformat(),
                        }
                    else:
                        order_response = {
                            "order_id": trade_obj._generate_order_id(),
                            "request_body": trade_obj.order,
                            "timestamp": datetime.now().isoformat(),
                        }
                    order_responses.append(order_response)

        self.save_orders(order_response_dict=order_responses)
        return order_responses

    def execute_orders(self, trade_obj: Trade) -> dict:
        """Executes a Trade Object via the broker."""
        order_dict = self.broker.place_order(
            account=self.trading_account, order=trade_obj.order
        )
        trade_obj._order_response = order_dict
        trade_obj._process_order_response()
        return order_dict

    def save_orders(self, order_response_dict: dict) -> bool:
        """Saves the order to a JSON file for further review."""
        def default(obj):
            if isinstance(obj, bytes):
                return str(obj)

        folder: pathlib.PurePath = pathlib.Path(__file__).parents[1].joinpath("data")

        if not folder.exists():
            folder.mkdir()

        file_path = folder.joinpath("orders.json")

        if file_path.exists():
            with open(file_path, "r") as order_json:
                orders_list = json.load(order_json)
        else:
            orders_list = []

        orders_list = orders_list + order_response_dict

        with open(file_path, mode="w+") as order_json:
            json.dump(obj=orders_list, fp=order_json, indent=4, default=default)

        return True

    def get_accounts(
        self, account_number: str = None, all_accounts: bool = False
    ) -> dict:
        """Returns all the account balances for a specified account."""
        account = self.trading_account or account_number
        return self.broker.get_account_info(account=account)

    def get_positions(
        self, account_number: str = None, all_accounts: bool = False
    ) -> List[Dict]:
        """Gets all the positions for a specified account number."""
        account = self.trading_account or account_number
        return self.broker.get_positions(account=account)
