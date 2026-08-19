"""Tests for the PaperBroker."""

import pytest

from pyrobot.brokers.paper_broker import PaperBroker


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

        sell_order = {
            "orderType": "MARKET",
            "orderLegCollection": [
                {
                    "instruction": "SELL",
                    "quantity": 10,
                    "instrument": {"symbol": "MSFT", "asset_type": "EQUITY"},
                }
            ],
        }
        response = paper_broker.place_order(account="TEST", order=sell_order)
        assert response["status"] == "FILLED"

    def test_insufficient_funds(self):
        broker = PaperBroker(initial_balance=100.0)
        broker.authenticate()
        broker.update_prices({"MSFT": {"close": 400.0}})

        order = {
            "orderType": "MARKET",
            "orderLegCollection": [
                {
                    "instruction": "BUY",
                    "quantity": 10,
                    "instrument": {"symbol": "MSFT", "asset_type": "EQUITY"},
                }
            ],
        }
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
