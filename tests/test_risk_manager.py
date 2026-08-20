"""Unit tests for RiskManager PnL calculation, position tracking, and risk controls."""

import pytest
from datetime import datetime, timezone
from pyrobot.exceptions import KillSwitchError, ExecutionError
from pyrobot.models.order import Order, OrderSide, OrderType, OrderState
from pyrobot.risk.manager import RiskManager
from pyrobot.risk.limits import RiskLimits
from pyrobot.risk.kill_switch import KillSwitch, KillSwitchReason


class TestRiskManagerPnLAndPositions:

    @pytest.fixture
    def risk_manager(self) -> RiskManager:
        return RiskManager(limits=RiskLimits.conservative())

    def test_initial_pnl_zero(self, risk_manager):
        assert risk_manager.daily_realized_pnl == 0.0

    def test_open_long_position_pnl_is_zero(self, risk_manager):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=100)
        pnl = risk_manager.record_fill(order, fill_price=150.0, fill_qty=100)
        assert pnl == 0.0
        assert risk_manager.daily_realized_pnl == 0.0
        positions = risk_manager.get_tracked_positions()
        assert positions["AAPL"]["qty"] == 100
        assert positions["AAPL"]["avg_price"] == 150.0

    def test_close_long_position_with_profit(self, risk_manager):
        # Open 100 @ 150
        buy_order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=100)
        risk_manager.record_fill(buy_order, fill_price=150.0, fill_qty=100)

        # Sell 100 @ 160 (profit = 100 * 10 = +1000)
        sell_order = Order(symbol="AAPL", side=OrderSide.SELL, quantity=100)
        pnl = risk_manager.record_fill(sell_order, fill_price=160.0, fill_qty=100, commission=5.0)

        assert pnl == 995.0
        assert risk_manager.daily_realized_pnl == 995.0
        positions = risk_manager.get_tracked_positions()
        assert positions["AAPL"]["qty"] == 0.0

    def test_close_long_position_with_loss(self, risk_manager):
        # Open 100 @ 150
        buy_order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=100)
        risk_manager.record_fill(buy_order, fill_price=150.0, fill_qty=100)

        # Sell 50 @ 140 (loss = 50 * -10 = -500)
        sell_order = Order(symbol="AAPL", side=OrderSide.SELL, quantity=50)
        pnl = risk_manager.record_fill(sell_order, fill_price=140.0, fill_qty=50)

        assert pnl == -500.0
        assert risk_manager.daily_realized_pnl == -500.0
        positions = risk_manager.get_tracked_positions()
        assert positions["AAPL"]["qty"] == 50
        assert positions["AAPL"]["avg_price"] == 150.0

    def test_short_position_profit(self, risk_manager):
        # Open short 50 @ 200
        short_order = Order(symbol="TSLA", side=OrderSide.SELL_SHORT, quantity=50)
        risk_manager.record_fill(short_order, fill_price=200.0, fill_qty=50)

        # Cover short 50 @ 180 (profit = 50 * (200 - 180) = +1000)
        cover_order = Order(symbol="TSLA", side=OrderSide.BUY_TO_COVER, quantity=50)
        pnl = risk_manager.record_fill(cover_order, fill_price=180.0, fill_qty=50, commission=2.0)

        assert pnl == 998.0
        assert risk_manager.daily_realized_pnl == 998.0
        positions = risk_manager.get_tracked_positions()
        assert positions["TSLA"]["qty"] == 0.0

    def test_sync_position(self, risk_manager):
        risk_manager.sync_position("MSFT", quantity=200, avg_price=300.0)
        positions = risk_manager.get_tracked_positions()
        assert positions["MSFT"]["qty"] == 200
        assert positions["MSFT"]["avg_price"] == 300.0

        # Sell 100 @ 310 (profit = 100 * 10 = +1000)
        sell_order = Order(symbol="MSFT", side=OrderSide.SELL, quantity=100)
        pnl = risk_manager.record_fill(sell_order, fill_price=310.0, fill_qty=100)
        assert pnl == 1000.0
        assert risk_manager.get_tracked_positions()["MSFT"]["qty"] == 100
