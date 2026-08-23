"""Unit tests for RiskManager PnL calculation, position tracking, and risk controls."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pyrobot.models.order import Order, OrderSide
from pyrobot.risk.limits import RiskLimits
from pyrobot.risk.manager import RiskManager


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


class TestModelRiskScale:

    @pytest.fixture
    def risk_manager(self) -> RiskManager:
        return RiskManager(limits=RiskLimits.conservative())

    @pytest.fixture
    def size_kwargs(self) -> dict:
        return dict(
            account_equity=100_000.0,
            win_rate=0.55,
            avg_win=0.03,
            avg_loss=0.02,
            price=150.0,
            method="fixed_fraction",
        )

    def test_default_scale_is_one(self, risk_manager):
        assert risk_manager.model_risk_scale == 1.0

    def test_scale_multiplies_calculated_size(self, risk_manager, size_kwargs):
        base = risk_manager.calculate_position_size(**size_kwargs)
        assert base > 0

        risk_manager.set_model_risk_scale(0.5, reason="model drift")
        scaled = risk_manager.calculate_position_size(**size_kwargs)

        assert scaled == int(base * 0.5)
        assert risk_manager.model_risk_scale == 0.5
        assert risk_manager.model_risk_scale_reason == "model drift"

    def test_zero_scale_halts_sizing(self, risk_manager, size_kwargs):
        risk_manager.set_model_risk_scale(0.0, reason="drift halt")
        assert risk_manager.calculate_position_size(**size_kwargs) == 0

    @pytest.mark.parametrize("bad_scale", [-0.1, 1.5, 2.0, float("nan")])
    def test_invalid_scale_raises(self, risk_manager, bad_scale):
        with pytest.raises(ValueError):
            risk_manager.set_model_risk_scale(bad_scale)
        assert risk_manager.model_risk_scale == 1.0

    def test_scale_exposed_in_status(self, risk_manager):
        risk_manager.set_model_risk_scale(0.75)
        assert risk_manager.status()["model_risk_scale"] == 0.75


class TestPositionSizingLimits:
    """De-magicked sizing parameters come from RiskLimits."""

    def _fixed_fraction_qty(self, limits: RiskLimits) -> int:
        rm = RiskManager(limits=limits)
        return rm.calculate_position_size(
            account_equity=100_000.0,
            win_rate=0.55,
            avg_win=0.03,
            avg_loss=0.02,
            price=150.0,
            method="fixed_fraction",
        )

    def test_per_trade_risk_pct_overrides_daily_loss_fallback(self):
        # Conservative: max_daily_loss_pct=0.01 → fallback risk 0.005.
        # Fixed-fraction: qty = equity * risk / (price * stop_pct).
        base = self._fixed_fraction_qty(RiskLimits.conservative())
        assert base == 166  # 100_000 * 0.005 / 3.0

        doubled = self._fixed_fraction_qty(
            replace(
                RiskLimits.conservative(),
                per_trade_risk_pct=0.01,
                max_single_order_value=250_000.0,  # avoid value-cap masking
            )
        )
        assert doubled == 333  # 100_000 * 0.01 / 3.0

    def test_default_stop_distance_pct_widens_stop(self):
        base = self._fixed_fraction_qty(RiskLimits.conservative())
        assert base == 166  # stop = 150 * 0.02 = 3.0

        wider_stop = self._fixed_fraction_qty(
            replace(RiskLimits.conservative(), default_stop_distance_pct=0.04)
        )
        assert wider_stop == 83  # 500 / 6.0

    def test_limits_validation_rejects_bad_sizing_params(self):
        with pytest.raises(ValueError):
            RiskLimits(default_stop_distance_pct=0.0).validate()
        with pytest.raises(ValueError):
            RiskLimits(per_trade_risk_pct=0.9).validate()
        RiskLimits(per_trade_risk_pct=None).validate()  # None is allowed


class TestCircuitBreakerHalfOpenWiring:

    @pytest.fixture
    def risk_manager(self) -> RiskManager:
        rm = RiskManager(limits=RiskLimits.conservative())
        rm.circuit_breaker.force_open("test")
        rm.circuit_breaker._opened_at = (
            datetime.now(timezone.utc) - timedelta(seconds=3600)
        )
        return rm

    def test_half_open_allows_exactly_one_test_order(self, risk_manager):
        order1 = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        approved1, reason1 = risk_manager.check_order(
            order1, {"AAPL": 0}, {"AAPL": 150.0}, 100_000.0
        )
        assert approved1, reason1

        order2 = Order(symbol="MSFT", side=OrderSide.BUY, quantity=10)
        approved2, reason2 = risk_manager.check_order(
            order2, {"MSFT": 0}, {"MSFT": 150.0}, 100_000.0
        )
        assert not approved2
        assert "Circuit breaker" in reason2

    def test_winning_fill_releases_test_slot(self, risk_manager):
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
        approved, _ = risk_manager.check_order(
            order, {"AAPL": 0}, {"AAPL": 150.0}, 100_000.0
        )
        assert approved

        risk_manager.record_fill(order, fill_price=150.0, fill_qty=10)
        assert risk_manager.circuit_breaker.is_closed

        order2 = Order(symbol="MSFT", side=OrderSide.BUY, quantity=10)
        approved2, reason2 = risk_manager.check_order(
            order2, {"MSFT": 0}, {"MSFT": 150.0}, 100_000.0
        )
        assert approved2, reason2
