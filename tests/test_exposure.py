"""Tests for pyrobot.risk.exposure — ExposureMonitor order projection."""

import pandas as pd
import pytest

from pyrobot.risk.exposure import ExposureMonitor, ExposureSnapshot
from pyrobot.risk.limits import RiskLimits

EQUITY = 100_000.0


def make_monitor(**limit_kwargs) -> ExposureMonitor:
    """Build an ExposureMonitor with limit overrides."""
    return ExposureMonitor(limits=RiskLimits(**limit_kwargs))


def make_snapshot(
    monitor: ExposureMonitor,
    positions: dict,
    prices: dict,
    equity: float = EQUITY,
) -> ExposureSnapshot:
    return monitor.calculate_exposure(
        positions=positions, prices=prices, account_equity=equity
    )


# ── SELL / BUY direction projection ──────────────────────────────────────────


class TestSellClosingLong:
    def test_sell_closing_long_passes_and_reduces_long_exposure(self):
        # Gross is at the 20% limit; closing a long must reduce gross,
        # not add short exposure (the old bug rejected this order).
        monitor = make_monitor(max_portfolio_exposure_pct=0.20)
        positions = {"AAPL": 100, "MSFT": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)
        assert snap.gross_exposure_pct == pytest.approx(0.20)

        allowed, reason = monitor.check_order(
            snap, "AAPL", "SELL", 100, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

        post = make_snapshot(monitor, {"AAPL": 0, "MSFT": 100}, prices)
        assert post.long_value == snap.long_value - 10_000.0
        assert post.short_value == 0.0
        assert post.gross_exposure_pct == pytest.approx(0.10)

    def test_sell_closing_long_ignores_short_limit(self):
        # Short exposure is at its 10% limit; closing a long must not be
        # counted as new short exposure.
        monitor = make_monitor(max_short_exposure_pct=0.10)
        positions = {"AAPL": 100, "TSLA": -100}
        prices = {"AAPL": 100.0, "TSLA": 100.0}
        snap = make_snapshot(monitor, positions, prices)
        assert snap.short_exposure_pct == pytest.approx(0.10)

        allowed, reason = monitor.check_order(
            snap, "AAPL", "SELL", 100, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

    def test_sell_beyond_holding_opens_short_for_excess_only(self):
        # Sell 150 against a 100-share long: 100 closes the long, the
        # 50-share excess opens short exposure.
        monitor = make_monitor(
            max_short_exposure_pct=0.10, max_position_size_pct=0.50
        )
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "AAPL", "SELL", 150, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason  # Excess short is 5k = 5% < 10% limit

        allowed, reason = monitor.check_order(
            snap, "AAPL", "SELL", 250, 100.0, EQUITY, positions=positions
        )
        assert not allowed
        assert "Short exposure" in reason  # Excess short is 15k = 15%


class TestSellWithNoLong:
    def test_sell_with_no_long_adds_short_exposure(self):
        monitor = make_monitor(max_short_exposure_pct=0.10)
        positions = {"MSFT": 100}
        prices = {"MSFT": 100.0, "TSLA": 50.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "TSLA", "SELL", 300, 50.0, EQUITY, positions=positions
        )
        assert not allowed
        assert "Short exposure" in reason  # 15k = 15% > 10% limit

    def test_sell_with_no_positions_data_adds_short_exposure(self):
        # No positions passed and no longs in the book → pure short.
        monitor = make_monitor(max_short_exposure_pct=0.05)
        prices = {"TSLA": 50.0}
        snap = make_snapshot(monitor, {}, prices)

        allowed, reason = monitor.check_order(
            snap, "TSLA", "SELL", 200, 50.0, EQUITY
        )
        assert not allowed
        assert "Short exposure" in reason


class TestBuyCoveringShort:
    def test_buy_covering_short_reduces_short_exposure(self):
        monitor = make_monitor(max_portfolio_exposure_pct=0.15)
        positions = {"TSLA": -100}
        prices = {"TSLA": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "TSLA", "BUY", 100, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

    def test_buy_beyond_cover_adds_long_for_excess_only(self):
        monitor = make_monitor(max_long_exposure_pct=0.10)
        positions = {"TSLA": -100}
        prices = {"TSLA": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        # Cover 100 + open 200 long = 20k long = 20% > 10% limit.
        allowed, reason = monitor.check_order(
            snap, "TSLA", "BUY", 300, 100.0, EQUITY, positions=positions
        )
        assert not allowed
        assert "Long exposure" in reason


# ── Symbol count ─────────────────────────────────────────────────────────────


class TestSymbolCount:
    def test_symbol_count_not_incremented_for_held_symbol(self):
        monitor = make_monitor(max_symbol_count=1)
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)
        assert snap.symbol_count == 1

        allowed, reason = monitor.check_order(
            snap, "AAPL", "BUY", 10, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

    def test_symbol_count_incremented_for_new_symbol(self):
        monitor = make_monitor(max_symbol_count=1)
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "MSFT", "BUY", 10, 100.0, EQUITY, positions=positions
        )
        assert not allowed
        assert "Symbol count" in reason


# ── Volatility limit enforcement ─────────────────────────────────────────────


class TestVolatilityEnforcement:
    def test_rejects_when_volatility_exceeds_limit(self):
        monitor = ExposureMonitor(
            limits=RiskLimits(max_volatility_threshold=0.50),
            volatility_by_symbol={"GME": 0.80},
        )
        prices = {"GME": 100.0}
        snap = make_snapshot(monitor, {}, prices)

        allowed, reason = monitor.check_order(
            snap, "GME", "BUY", 10, 100.0, EQUITY, positions={}
        )
        assert not allowed
        assert "Volatility" in reason
        assert "GME" in reason

    def test_passes_when_volatility_map_absent(self):
        monitor = ExposureMonitor(limits=RiskLimits(max_volatility_threshold=0.50))
        prices = {"GME": 100.0}
        snap = make_snapshot(monitor, {}, prices)

        allowed, reason = monitor.check_order(
            snap, "GME", "BUY", 10, 100.0, EQUITY, positions={}
        )
        assert allowed, reason

    def test_passes_when_symbol_missing_from_map(self):
        monitor = ExposureMonitor(
            limits=RiskLimits(max_volatility_threshold=0.50),
            volatility_by_symbol={"GME": 0.80},
        )
        prices = {"AAPL": 100.0}
        snap = make_snapshot(monitor, {}, prices)

        allowed, reason = monitor.check_order(
            snap, "AAPL", "BUY", 10, 100.0, EQUITY, positions={}
        )
        assert allowed, reason

    def test_setter_updates_volatility_data(self):
        monitor = ExposureMonitor(limits=RiskLimits(max_volatility_threshold=0.50))
        prices = {"GME": 100.0}
        snap = make_snapshot(monitor, {}, prices)

        monitor.set_volatility_by_symbol({"GME": 0.80})
        allowed, reason = monitor.check_order(
            snap, "GME", "BUY", 10, 100.0, EQUITY, positions={}
        )
        assert not allowed
        assert "Volatility" in reason


# ── Correlation limit enforcement ────────────────────────────────────────────


def correlation_matrix(aapl_msft: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"AAPL": [1.0, aapl_msft], "MSFT": [aapl_msft, 1.0]},
        index=["AAPL", "MSFT"],
    )


class TestCorrelationEnforcement:
    def test_rejects_new_symbol_correlated_with_held_symbol(self):
        monitor = ExposureMonitor(
            limits=RiskLimits(max_correlation_threshold=0.85),
            correlation_matrix=correlation_matrix(0.9),
        )
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "MSFT", "BUY", 10, 100.0, EQUITY, positions=positions
        )
        assert not allowed
        assert "Correlation" in reason
        assert "AAPL" in reason and "MSFT" in reason

    def test_passes_when_correlation_below_threshold(self):
        monitor = ExposureMonitor(
            limits=RiskLimits(max_correlation_threshold=0.85),
            correlation_matrix=correlation_matrix(0.5),
        )
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "MSFT", "BUY", 10, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

    def test_passes_when_matrix_absent(self):
        monitor = ExposureMonitor(limits=RiskLimits(max_correlation_threshold=0.85))
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "MSFT", "BUY", 10, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

    def test_passes_when_symbol_missing_from_matrix(self):
        monitor = ExposureMonitor(
            limits=RiskLimits(max_correlation_threshold=0.85),
            correlation_matrix=correlation_matrix(0.9),
        )
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0, "NVDA": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "NVDA", "BUY", 10, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

    def test_setter_updates_correlation_matrix(self):
        monitor = ExposureMonitor(limits=RiskLimits(max_correlation_threshold=0.85))
        positions = {"AAPL": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        monitor.set_correlation_matrix(correlation_matrix(0.9))
        allowed, reason = monitor.check_order(
            snap, "MSFT", "BUY", 10, 100.0, EQUITY, positions=positions
        )
        assert not allowed
        assert "Correlation" in reason


# ── Sector concentration on reducing orders ──────────────────────────────────


class TestSectorConcentration:
    def test_reducing_order_does_not_add_sector_concentration(self):
        sector_map = {"AAPL": "TECH", "MSFT": "TECH"}
        monitor = ExposureMonitor(
            limits=RiskLimits(max_sector_concentration_pct=0.20),
            sector_map=sector_map,
        )
        positions = {"AAPL": 100, "MSFT": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)
        assert snap.sector_exposure["TECH"] == pytest.approx(20_000.0)

        # Closing the AAPL long releases TECH concentration headroom.
        allowed, reason = monitor.check_order(
            snap, "AAPL", "SELL", 100, 100.0, EQUITY, positions=positions
        )
        assert allowed, reason

    def test_increasing_order_still_enforces_sector_concentration(self):
        sector_map = {"AAPL": "TECH", "MSFT": "TECH"}
        monitor = ExposureMonitor(
            limits=RiskLimits(max_sector_concentration_pct=0.20),
            sector_map=sector_map,
        )
        positions = {"AAPL": 100, "MSFT": 100}
        prices = {"AAPL": 100.0, "MSFT": 100.0}
        snap = make_snapshot(monitor, positions, prices)

        allowed, reason = monitor.check_order(
            snap, "AAPL", "BUY", 50, 100.0, EQUITY, positions=positions
        )
        assert not allowed
        assert "Sector" in reason
