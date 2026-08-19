"""Tests for the Portfolio class."""

import pytest

from pyrobot.portfolio import Portfolio


class TestPortfolio:
    """Tests for Portfolio management."""

    def test_add_position(self):
        portfolio = Portfolio()
        pos = portfolio.add_position(
            symbol="MSFT",
            asset_type="equity",
            quantity=10,
            purchase_price=400.0,
            purchase_date="2024-01-01",
        )
        assert pos["symbol"] == "MSFT"
        assert pos["quantity"] == 10
        assert pos["ownership_status"] is True

    def test_add_positions_multiple(self):
        portfolio = Portfolio()
        positions = [
            {"symbol": "MSFT", "asset_type": "equity", "quantity": 10, "purchase_price": 400.0},
            {"symbol": "AAPL", "asset_type": "equity", "quantity": 5, "purchase_price": 180.0},
        ]
        result = portfolio.add_positions(positions=positions)
        assert len(result) == 2
        assert "MSFT" in result
        assert "AAPL" in result

    def test_add_positions_not_list_raises(self):
        portfolio = Portfolio()
        with pytest.raises(TypeError):
            portfolio.add_positions(positions="not a list")

    def test_remove_position(self):
        portfolio = Portfolio()
        portfolio.add_position(symbol="MSFT", asset_type="equity")
        success, msg = portfolio.remove_position(symbol="MSFT")
        assert success is True
        assert "MSFT" in msg

    def test_remove_nonexistent(self):
        portfolio = Portfolio()
        success, msg = portfolio.remove_position(symbol="AAPL")
        assert success is False

    def test_in_portfolio(self):
        portfolio = Portfolio()
        portfolio.add_position(symbol="MSFT", asset_type="equity")
        assert portfolio.in_portfolio(symbol="MSFT") is True
        assert portfolio.in_portfolio(symbol="AAPL") is False

    def test_ownership_status(self):
        portfolio = Portfolio()
        portfolio.add_position(
            symbol="MSFT", asset_type="equity", purchase_date="2024-01-01"
        )
        assert portfolio.get_ownership_status(symbol="MSFT") is True

    def test_set_ownership_status(self):
        portfolio = Portfolio()
        portfolio.add_position(symbol="MSFT", asset_type="equity")
        portfolio.set_ownership_status(symbol="MSFT", ownership=False)
        assert portfolio.get_ownership_status(symbol="MSFT") is False

    def test_set_ownership_nonexistent_raises(self):
        portfolio = Portfolio()
        with pytest.raises(KeyError):
            portfolio.set_ownership_status(symbol="AAPL", ownership=True)

    def test_is_profitable(self):
        portfolio = Portfolio()
        portfolio.add_position(
            symbol="MSFT",
            asset_type="equity",
            purchase_price=400.0,
            purchase_date="2024-01-01",
        )
        assert portfolio.is_profitable(symbol="MSFT", current_price=410.0) is True
        assert portfolio.is_profitable(symbol="MSFT", current_price=390.0) is False

    def test_total_allocation_returns_dict(self):
        portfolio = Portfolio()
        portfolio.add_position(symbol="MSFT", asset_type="stocks")
        portfolio.add_position(symbol="TLT", asset_type="fixed_income")
        result = portfolio.total_allocation()
        assert isinstance(result, dict)
        assert len(result["stocks"]) == 1
        assert len(result["fixed_income"]) == 1

    def test_portfolio_variance(self):
        import numpy as np
        import pandas as pd

        portfolio = Portfolio()
        weights = {"A": 0.5, "B": 0.5}
        cov_matrix = pd.DataFrame(
            [[0.04, 0.01], [0.01, 0.09]], index=["A", "B"], columns=["A", "B"]
        )
        variance = portfolio.portfolio_variance(weights=weights, covariance_matrix=cov_matrix)
        assert isinstance(variance, float)
        assert variance > 0
