Excellent choices. Abstract broker layer + selective improvements is the most pragmatic and extensible approach. Let me compile the full development plan based on everything I've found.
Development Plan: Python Trading Robot Modernization
Executive Summary
Modernize the python-trading-robot by: (1) introducing a broker abstraction layer so the system is broker-agnostic, (2) fixing critical bugs in indicator calculations and signal execution, (3) updating dependencies and infrastructure, and (4) adding proper testing with mocks. The existing PyRobot/Portfolio/StockFrame/Indicators architecture is preserved; the broker-specific code and signal execution logic are rewritten.
Phase 0: Critical Bug Fixes (Pre-requisite)
These bugs must be fixed before any new feature work, as they break core functionality.
0.1 - Missing __init__.py
File: pyrobot/__init__.py (create)
- The pyrobot package has no __init__.py, making it impossible to import as a proper Python package in many contexts.
0.2 - Bollinger Bands Formula Incorrect
File: pyrobot/indicators.py:454-461
- Upper band: 4 * (std/mean) is not standard Bollinger. Should be mean + (2 * std).
- Lower band: formula is garbled with wrong operator precedence. Should be mean - (2 * std).
0.3 - Stochastic Oscillator Formula Broken
File: pyrobot/indicators.py:555-558
- Missing parentheses causes incorrect operator precedence: close - low / high - low evaluates as close - (low/high) - low. Should be (close - low) / (high - low) * 100.
0.4 - Commodity Channel Index References Non-existent Column
File: pyrobot/indicators.py:803,808
- References self._frame['pp'] which doesn't exist. Should be self._frame['typical_price'].
- Also the CCI formula itself is wrong (just mean/std instead of the standard (typical_price - SMA) / (0.015 * mean_deviation)).
0.5 - KST Oscillator Bug
File: pyrobot/indicators.py:990-991
- self._frame['column_name'] is a string literal, not the variable. Should be self._frame[column_name].
- .rolling() is called without a window parameter.
0.6 - Signal Execution Logic Bug (Critical)
File: pyrobot/robot.py:748
- Uses elif for sell signals, meaning sells are never checked if any buy condition exists (even if empty). Should be if not sells.empty: (independent block).
0.7 - save_orders Path Bug
File: pyrobot/robot.py:863,872
- Uses relative path 'data/orders.json' for read/write but pathlib.Path for existence check. Will fail depending on CWD. Should use file_path consistently.
0.8 - total_allocation Missing Return
File: pyrobot/portfolio.py:203
- Method builds total_allocation dict but never returns it.
0.9 - OrderStatus.is_cancelled Wrong Status
File: pyrobot/order_status.py:32
- Checks for 'FILLED' instead of 'CANCELLED'.
0.10 - Deprecated datetime.utcnow()
File: pyrobot/robot.py:109,121,152,164,195,207
- datetime.utcnow() is deprecated in Python 3.12+. Replace with datetime.now(timezone.utc).
Phase 1: Broker Abstraction Layer
1.1 - Define BrokerInterface Abstract Base Class
New file: pyrobot/brokers/base.py
from abc import ABC, abstractmethod

class BrokerInterface(ABC):
    """Abstract base class for all broker adapters."""
    
    @abstractmethod
    def authenticate(self) -> bool: ...
    
    @abstractmethod
    def get_quotes(self, symbols: List[str]) -> dict: ...
    
    @abstractmethod
    def get_historical_prices(self, symbol: str, start: datetime, end: datetime, 
                               bar_size: int, bar_type: str) -> List[dict]: ...
    
    @abstractmethod
    def place_order(self, account: str, order: dict) -> dict: ...
    
    @abstractmethod
    def get_order_status(self, account: str, order_id: str) -> dict: ...
    
    @abstractmethod
    def get_account_info(self, account: str = None) -> dict: ...
    
    @abstractmethod
    def get_positions(self, account: str = None) -> List[dict]: ...
    
    @abstractmethod
    def get_option_chain(self, symbol: str) -> dict: ...
    
    @property
    @abstractmethod
    def name(self) -> str: ...
1.2 - Implement SchwabBroker Adapter
New file: pyrobot/brokers/schwab_broker.py
- Wraps schwab-py library (requires Python >=3.10)
- Handles OAuth 2.0 authentication via Schwab Developer Portal
- Maps Schwab API responses to the internal dict format the rest of the system expects
- WebSocket streaming support for real-time quotes
1.3 - Implement AlpacaBroker Adapter
New file: pyrobot/brokers/alpaca_broker.py
- Wraps alpaca-py or direct REST API calls
- API key + secret authentication
- Commission-free US equities/ETFs
- Built-in paper trading mode
1.4 - Implement IBKRBroker Adapter
New file: pyrobot/brokers/ibkr_broker.py
- Wraps ib_insync or ib_async
- Requires TWS or IB Gateway running locally
- Most complex setup but broadest market access
1.5 - Implement PaperBroker (Local Simulator)
New file: pyrobot/brokers/paper_broker.py
- No external API calls
- Simulates order execution against provided price data
- Tracks virtual portfolio, P&L, order history
- Useful for testing strategies without any broker account
1.6 - Create Broker Factory
New file: pyrobot/brokers/__init__.py
def create_broker(broker_name: str, **kwargs) -> BrokerInterface:
    """Factory to instantiate the correct broker adapter."""
    brokers = {
        'schwab': SchwabBroker,
        'alpaca': AlpacaBroker,
        'ibkr': IBKRBroker,
        'paper': PaperBroker,
    }
    if broker_name not in brokers:
        raise ValueError(f"Unknown broker: {broker_name}. Available: {list(brokers.keys())}")
    return brokers[broker_name](**kwargs)
1.7 - Refactor PyRobot to Accept BrokerInterface
File: pyrobot/robot.py (modify)
- Constructor takes a broker: BrokerInterface instead of client_id/redirect_uri/credentials_path
- All API calls go through self.broker.get_quotes(), self.broker.place_order(), etc.
- Keep backward-compatible constructor signature with deprecation warnings
- Remove direct td.client.TDClient dependency
Phase 2: Refactor & Improve Existing Components
2.1 - Fix Indicators Class
- Fix all bugs from Phase 0
- Add adx(), vwap(), ichimoku_cloud(), obv() indicator methods
- Add proper input validation on all indicator parameters
- Clean up temporary columns more robustly (use context manager or track columns per indicator)
2.2 - Improve StockFrame
- Add column validation on construction
- Add add_rows method that handles both dict and list inputs
- Add historical data persistence (SQLite backing)
- Fix grab_n_bars_ago edge cases (n > available bars)
2.3 - Refactor Trade Class
- Fix add_leg which initializes leg = {} then tries to set nested keys without initializing them
- Add __repr__ and __str__ for better debugging
- Support OCO orders more cleanly (current implementation wraps existing orders incorrectly)
- Add order validation before submission
2.4 - Refactor Portfolio Class
- Fix total_allocation missing return
- Reduce code duplication in _parse_account_balances / _parse_account_positions
- Add portfolio persistence (save/load to JSON)
- Add Sharpe ratio, Sortino ratio, max drawdown calculations
- Add position sizing methods (Kelly criterion, fixed fractional, etc.)
2.5 - Add Comprehensive Logging
New file: pyrobot/logging_config.py
- Replace all print() statements with proper logging module usage
- Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- File + console handlers
- Trade execution logging with timestamps
2.6 - Add Error Handling
- Replace bare except: with specific exception types
- Add retry logic with exponential backoff for API calls
- Add rate limiting awareness (TD had 120 req/min, Alpaca has 200 req/min)
- Custom exception hierarchy: BrokerError, AuthenticationError, OrderRejectedError, etc.
Phase 3: Modernize Infrastructure
3.1 - Add pyproject.toml
New file: pyproject.toml
- Replace setup.py with modern pyproject.toml (PEP 621)
- Define optional dependency groups:
- [broker.schwab]: schwab-py
- [broker.alpaca]: alpaca-py
- [broker.ibkr]: ib_insync
- [dev]: pytest, pytest-cov, pytest-mock, mypy, ruff
- Support Python >=3.10 (for async/await, match statements, modern typing)
3.2 - Update Dependencies
- pandas>=2.0 (drop pinned version)
- numpy>=1.24 (drop pinned version)
- Remove td-ameritrade-python-api from required deps
- Add python-dotenv for environment-based config
- Add type stubs for mypy
3.3 - Configuration Modernization
- Support .env files via python-dotenv
- Support YAML/JSON config alongside INI
- Environment variable override for all settings
- Secrets never stored in config files
3.4 - Add Type Hints Throughout
- All public methods get full type annotations
- Add py.typed marker for PEP 561 compliance
- Configure mypy in pyproject.toml
Phase 4: Testing & CI
4.1 - Rewrite Tests with Mocks
Files: tests/*.py (rewrite)
- Create tests/conftest.py with shared fixtures and mock broker
- Mock all API calls (no live credentials needed)
- Add unit tests for each indicator calculation with known values
- Add integration tests using PaperBroker
- Achieve >80% code coverage
4.2 - Add Backtesting Support
New file: pyrobot/backtesting/engine.py
- Feed historical data through the same indicator/signal/execution pipeline
- Track virtual positions, P&L, win rate, Sharpe ratio
- Generate HTML performance reports
4.3 - CI Pipeline
File: .github/workflows/ci.yml (new/modify)
- Run tests on Python 3.10, 3.11, 3.12, 3.13
- Run mypy type checking
- Run ruff linting
- Code coverage reporting
Phase 5: Documentation & Samples
5.1 - Update README
- Document the broker abstraction layer
- Add quickstart for each supported broker
- Update installation instructions
5.2 - Update Sample Scripts
- samples/trading_robot.py → use broker factory, show Alpaca and Schwab examples
- Add samples/backtest_golden_cross.py → backtest the documented strategy
- Add samples/paper_trading.py → demo with PaperBroker
5.3 - Fill Empty Doc Pages
- docs/algo_trading.md → general algo trading concepts
- docs/portfolio_object.md → Portfolio API reference
- docs/trade_object.md → Trade API reference
File Change Summary
Action	File	Description
CREATE	pyrobot/__init__.py	Package init
CREATE	pyrobot/brokers/__init__.py	Broker factory
CREATE	pyrobot/brokers/base.py	Abstract broker interface
CREATE	pyrobot/brokers/schwab_broker.py	Schwab adapter
CREATE	pyrobot/brokers/alpaca_broker.py	Alpaca adapter
CREATE	pyrobot/brokers/ibkr_broker.py	IBKR adapter
CREATE	pyrobot/brokers/paper_broker.py	Paper trading simulator
CREATE	pyrobot/exceptions.py	Custom exception hierarchy
CREATE	pyrobot/logging_config.py	Logging configuration
CREATE	pyrobot/backtesting/engine.py	Backtesting engine
CREATE	pyproject.toml	Modern package config
CREATE	tests/conftest.py	Shared test fixtures
MODIFY	pyrobot/robot.py	Broker abstraction, bug fixes
MODIFY	pyrobot/indicators.py	Fix all indicator bugs, add indicators
MODIFY	pyrobot/trades.py	Bug fixes, validation, add_leg fix
MODIFY	pyrobot/portfolio.py	Fix bugs, add metrics, reduce duplication
MODIFY	pyrobot/stock_frame.py	Edge case fixes, validation
MODIFY	pyrobot/order_status.py	Fix is_cancelled status
MODIFY	tests/test_*.py	Rewrite with mocks
MODIFY	samples/*.py	Update to use broker factory
MODIFY	setup.py	Add deprecation notice
MODIFY	README.md	Updated documentation
Estimated Complexity & Priority
Phase	Effort	Priority
Phase 0: Bug Fixes	Low-Medium	Critical
Phase 1: Broker Abstraction	Medium-High	High
Phase 2: Component Refactor	Medium	High
Phase 3: Infrastructure	Medium	Medium
Phase 4: Testing & CI	Medium	High
Phase 5: Documentation	Low	Low
Key Design Decisions
1. Broker Interface Pattern: Each broker implements the same BrokerInterface. PyRobot holds a reference to one, never touches the broker SDK directly.
2. Response Normalization: Each broker adapter normalizes API responses to a common dict format ({'symbol', 'open', 'close', 'high', 'low', 'volume', 'datetime'}) before returning.
3. Backward Compatibility: The old PyRobot(client_id=..., redirect_uri=...) constructor will still work via a TDAmeritradeBroker adapter that can be a shim over Schwab's API or raise a clear deprecation error.
4. Optional Dependencies: Broker libraries are optional extras (pip install python-trading-robot[alpaca]), not hard requirements. This keeps the core lightweight.
▣  Plan · Big Pickle · 9m 15s