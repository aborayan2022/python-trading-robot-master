"""Tests for the StockFrame class."""

import pandas as pd
import pytest

from pyrobot.stock_frame import StockFrame


class TestStockFrame:
    """Tests for StockFrame creation and manipulation."""

    def test_creates_multi_index(self, stock_frame):
        assert isinstance(stock_frame.frame.index, pd.MultiIndex)

    def test_index_levels(self, stock_frame):
        assert stock_frame.frame.index.names == ["symbol", "datetime"]

    def test_has_ohlc_columns(self, stock_frame):
        for col in ["open", "close", "high", "low", "volume"]:
            assert col in stock_frame.frame.columns

    def test_symbol_groups(self, stock_frame):
        groups = stock_frame.symbol_groups
        assert groups is not None

    def test_add_rows(self, stock_frame):
        new_bars = [
            {
                "symbol": "MSFT",
                "open": 405.0,
                "close": 406.0,
                "high": 407.0,
                "low": 404.0,
                "volume": 50000,
                "datetime": 1704219000000,
            }
        ]
        initial_len = len(stock_frame.frame)
        stock_frame.add_rows(data=new_bars)
        assert len(stock_frame.frame) >= initial_len

    def test_multi_symbol_groups(self, stock_frame_multi):
        symbols = stock_frame_multi.frame.index.get_level_values(0).unique()
        assert len(symbols) == 2
        assert "MSFT" in symbols
        assert "AAPL" in symbols

    def test_do_indicator_exist_passes(self, stock_frame):
        assert stock_frame.do_indicator_exist(["open", "close"]) is True

    def test_do_indicator_exist_raises(self, stock_frame):
        with pytest.raises(KeyError):
            stock_frame.do_indicator_exist(["nonexistent_column"])

    def test_grab_current_bar(self, stock_frame):
        bar = stock_frame.grab_current_bar("MSFT")
        assert bar is not None
        assert len(bar) > 0
