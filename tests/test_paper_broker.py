"""Tests for the PaperBroker."""

import pytest

from pyrobot.brokers.paper_broker import PaperBroker


def make_order(
    instruction: str,
    quantity: int,
    symbol: str = "MSFT",
    order_type: str = "MARKET",
    price: float = 0.0,
    stop_price: float = 0.0,
) -> dict:
    """Build a canonical order dict for the paper broker."""
    order = {
        "orderType": order_type,
        "session": "NORMAL",
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": instruction,
                "quantity": quantity,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"},
            }
        ],
    }
    if price:
        order["price"] = price
    if stop_price:
        order["stopPrice"] = stop_price
    return order


class TestPaperBroker:
    """Tests for PaperBroker functionality."""

    def test_authenticate(self, paper_broker):
        assert paper_broker._authenticated is True
        assert paper_broker.name == "paper"

    def test_initial_balance(self, paper_broker):
        info = paper_broker.get_account_info()
        assert info["cash_balance"] == 100_000.0
        assert info["buying_power"] == 100_000.0

    def test_place_buy_order(self, paper_broker, market_order):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(account="TEST", order=market_order)

        assert response["status"] == "FILLED"
        assert response["order_id"] != ""

        info = paper_broker.get_account_info()
        assert info["cash_balance"] < 100_000.0

    def test_place_sell_order(self, paper_broker, market_order):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=market_order)

        sell_order = make_order("SELL", 10)
        response = paper_broker.place_order(account="TEST", order=sell_order)
        assert response["status"] == "FILLED"

    def test_insufficient_funds(self):
        broker = PaperBroker(initial_balance=100.0)
        broker.authenticate()
        broker.update_prices({"MSFT": {"close": 400.0}})

        order = make_order("BUY", 10)
        response = broker.place_order(account="TEST", order=order)
        assert response["status"] == "REJECTED"

    def test_no_price_rejects(self, paper_broker, market_order):
        response = paper_broker.place_order(account="TEST", order=market_order)
        assert response["status"] == "REJECTED"

    def test_positions_tracking(self, paper_broker, market_order):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=market_order)

        positions = paper_broker.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "MSFT"
        assert positions[0]["quantity"] == 10

    def test_order_history(self, paper_broker, market_order):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=market_order)

        assert len(paper_broker.order_history) == 1
        assert paper_broker.order_history[0]["symbol"] == "MSFT"

    def test_get_quotes(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0, "open": 399.0}})
        quotes = paper_broker.get_quotes(["MSFT"])

        assert "MSFT" in quotes
        assert quotes["MSFT"]["last_price"] == 400.0

    def test_get_order_status(self, paper_broker, market_order):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(account="TEST", order=market_order)

        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "FILLED"

    def test_portfolio_summary(self, paper_broker, market_order):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=market_order)

        summary = paper_broker.portfolio_summary
        assert summary["initial_balance"] == 100_000.0
        assert summary["positions_count"] == 1


class TestPaperBrokerShortLifecycle:
    """Short selling must be tracked as a liability, not free cash."""

    def test_sell_short_credits_cash_and_tracks_liability(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("SELL_SHORT", 100)
        )

        assert response["status"] == "FILLED"
        info = paper_broker.get_account_info()
        assert info["cash_balance"] == pytest.approx(140_000.0)
        assert info["short_market_value"] == pytest.approx(40_000.0)
        # Equity unchanged: cash credit offset by the short liability.
        assert info["equity"] == pytest.approx(100_000.0)

        positions = [p for p in paper_broker.get_positions() if p["quantity"] < 0]
        assert len(positions) == 1
        assert positions[0]["symbol"] == "MSFT"
        assert positions[0]["quantity"] == -100
        assert positions[0]["average_price"] == pytest.approx(400.0)

    def test_short_market_value_follows_price(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=make_order("SELL_SHORT", 100))

        paper_broker.update_prices({"MSFT": {"close": 380.0}})
        info = paper_broker.get_account_info()
        assert info["short_market_value"] == pytest.approx(38_000.0)
        assert info["equity"] == pytest.approx(102_000.0)

    def test_buy_to_cover_closes_short_and_realizes_pnl(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=make_order("SELL_SHORT", 100))

        paper_broker.update_prices({"MSFT": {"close": 380.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("BUY_TO_COVER", 100)
        )
        assert response["status"] == "FILLED"

        info = paper_broker.get_account_info()
        assert info["cash_balance"] == pytest.approx(102_000.0)
        assert info["short_market_value"] == pytest.approx(0.0)
        assert info["equity"] == pytest.approx(102_000.0)
        assert paper_broker.portfolio_summary["realized_pnl"] == pytest.approx(2_000.0)

    def test_buy_to_cover_rejected_without_short(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("BUY_TO_COVER", 10)
        )
        assert response["status"] == "REJECTED"

    def test_sell_beyond_holdings_shorts_the_excess(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=make_order("BUY", 10))
        response = paper_broker.place_order(
            account="TEST", order=make_order("SELL", 15)
        )
        assert response["status"] == "FILLED"

        info = paper_broker.get_account_info()
        assert info["long_market_value"] == pytest.approx(0.0)
        assert info["short_market_value"] == pytest.approx(5 * 400.0)
        # Buy 10 @400 (-4000), sell 10 long (+4000), short 5 (+2000).
        assert info["cash_balance"] == pytest.approx(102_000.0)
        assert info["equity"] == pytest.approx(100_000.0)


class TestPaperBrokerLimitOrders:
    """LIMIT orders must fill conditionally, never unconditionally."""

    def test_buy_limit_below_market_stays_open_then_fills(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("BUY", 10, order_type="LIMIT", price=395.0)
        )

        # Buy limit 395 with market at 400 must NOT fill instantly.
        assert response["status"] == "OPEN"
        assert paper_broker.get_account_info()["cash_balance"] == 100_000.0
        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "OPEN"
        assert status["filled_quantity"] == 0
        assert status["remaining_quantity"] == 10

        # Price drops to the limit -> fills at the new price.
        paper_broker.update_prices({"MSFT": {"close": 394.5}})
        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "FILLED"
        assert status["avg_fill_price"] == pytest.approx(394.5)
        assert paper_broker.get_account_info()["cash_balance"] == pytest.approx(
            100_000.0 - 3_945.0
        )

    def test_marketable_buy_limit_fills_at_best_price(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("BUY", 10, order_type="LIMIT", price=405.0)
        )

        assert response["status"] == "FILLED"
        status = paper_broker.get_order_status("TEST", response["order_id"])
        # Fills at min(limit, last) = 400, not at the limit price.
        assert status["avg_fill_price"] == pytest.approx(400.0)

    def test_sell_limit_below_market_stays_open(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=make_order("BUY", 10))

        response = paper_broker.place_order(
            account="TEST",
            order=make_order("SELL", 10, order_type="LIMIT", price=410.0),
        )
        assert response["status"] == "OPEN"
        cash_after_buy = paper_broker.get_account_info()["cash_balance"]

        paper_broker.update_prices({"MSFT": {"close": 411.0}})
        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "FILLED"
        assert status["avg_fill_price"] == pytest.approx(411.0)
        assert paper_broker.get_account_info()["cash_balance"] == pytest.approx(
            cash_after_buy + 10 * 411.0
        )


class TestPaperBrokerStopOrders:
    """STOP orders must trigger only on a price cross."""

    def test_buy_stop_rests_until_price_rises(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 390.0}})
        response = paper_broker.place_order(
            account="TEST",
            order=make_order("BUY", 10, order_type="STOP", stop_price=395.0),
        )
        assert response["status"] == "OPEN"

        paper_broker.update_prices({"MSFT": {"close": 396.0}})
        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "FILLED"
        assert status["avg_fill_price"] == pytest.approx(396.0)

    def test_sell_stop_rests_until_price_falls(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        paper_broker.place_order(account="TEST", order=make_order("BUY", 10))

        response = paper_broker.place_order(
            account="TEST",
            order=make_order("SELL", 10, order_type="STOP", stop_price=385.0),
        )
        assert response["status"] == "OPEN"

        paper_broker.update_prices({"MSFT": {"close": 384.0}})
        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "FILLED"
        assert status["avg_fill_price"] == pytest.approx(384.0)


class TestPaperBrokerCancelOrder:
    """cancel_order semantics for resting and terminal orders."""

    def test_cancel_open_limit_order(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("BUY", 10, order_type="LIMIT", price=390.0)
        )
        assert len(paper_broker.get_open_orders()) == 1

        assert paper_broker.cancel_order(response["order_id"]) is True
        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "CANCELLED"
        assert paper_broker.get_open_orders() == []
        # Cash untouched by a cancelled order.
        assert paper_broker.get_account_info()["cash_balance"] == 100_000.0

        # Cancel is not idempotent on terminal orders.
        assert paper_broker.cancel_order(response["order_id"]) is False

    def test_cancel_filled_order_returns_false(self, paper_broker, market_order):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(account="TEST", order=market_order)
        assert response["status"] == "FILLED"

        # Market orders fill instantly, so there is nothing to cancel.
        assert paper_broker.cancel_order(response["order_id"]) is False

    def test_cancel_unknown_order_returns_false(self, paper_broker):
        assert paper_broker.cancel_order("nope") is False


class TestPaperBrokerOrderStatus:
    """get_order_status must expose the reconciler's required keys."""

    def test_status_keys_on_filled_order(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("BUY", 10)
        )

        status = paper_broker.get_order_status("TEST", response["order_id"])
        for key in (
            "status",
            "quantity",
            "filled_quantity",
            "avg_fill_price",
            "remaining_quantity",
        ):
            assert key in status, f"missing key: {key}"
        assert status["status"] == "FILLED"
        assert status["quantity"] == 10
        assert status["filled_quantity"] == 10
        assert status["avg_fill_price"] == pytest.approx(400.0)
        assert status["remaining_quantity"] == 0

    def test_status_keys_on_open_order(self, paper_broker):
        paper_broker.update_prices({"MSFT": {"close": 400.0}})
        response = paper_broker.place_order(
            account="TEST", order=make_order("BUY", 10, order_type="LIMIT", price=390.0)
        )

        status = paper_broker.get_order_status("TEST", response["order_id"])
        assert status["status"] == "OPEN"
        assert status["filled_quantity"] == 0
        assert status["avg_fill_price"] == 0.0
        assert status["remaining_quantity"] == 10


class TestPaperBrokerCommission:
    """Optional per-trade commission reduces cash on each fill."""

    def test_commission_charged_on_buy(self):
        broker = PaperBroker(
            initial_balance=100_000.0, commission_per_trade=1.5
        )
        broker.authenticate()
        broker.update_prices({"MSFT": {"close": 400.0}})
        response = broker.place_order(
            account="TEST", order=make_order("BUY", 10)
        )

        assert response["status"] == "FILLED"
        assert broker.get_account_info()["cash_balance"] == pytest.approx(
            100_000.0 - 4_000.0 - 1.5
        )

    def test_commission_charged_on_short_sell_and_cover(self):
        broker = PaperBroker(
            initial_balance=100_000.0, commission_per_trade=1.0
        )
        broker.authenticate()
        broker.update_prices({"MSFT": {"close": 400.0}})
        broker.place_order(account="TEST", order=make_order("SELL_SHORT", 10))

        # Short proceeds credited minus commission.
        assert broker.get_account_info()["cash_balance"] == pytest.approx(
            100_000.0 + 4_000.0 - 1.0
        )

        broker.place_order(account="TEST", order=make_order("BUY_TO_COVER", 10))
        assert broker.get_account_info()["cash_balance"] == pytest.approx(
            100_000.0 - 2.0
        )

    def test_commission_counts_towards_insufficient_funds(self):
        broker = PaperBroker(initial_balance=4_000.0, commission_per_trade=0.01)
        broker.authenticate()
        broker.update_prices({"MSFT": {"close": 400.0}})
        response = broker.place_order(
            account="TEST", order=make_order("BUY", 10)
        )
        assert response["status"] == "REJECTED"
