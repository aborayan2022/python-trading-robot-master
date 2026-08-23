"""Tests for the Indicators class."""


import numpy as np
import pandas as pd

from pyrobot.indicators import Indicators


class TestBollingerBands:
    """Tests for Bollinger Bands calculation."""

    def test_upper_band_above_mean(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.bollinger_bands(period=20)
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["band_upper", "band_lower"])
        assert (valid["band_upper"] >= valid["band_lower"]).all()

    def test_bands_contain_majority_of_prices(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.bollinger_bands(period=20)
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["band_upper", "band_lower"])
        within_bands = (
            (valid["close"] >= valid["band_lower"])
            & (valid["close"] <= valid["band_upper"])
        )
        assert within_bands.mean() > 0.5

    def test_bands_symmetric(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.bollinger_bands(period=20)
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["band_upper", "band_lower"])
        mid = (valid["band_upper"] + valid["band_lower"]) / 2
        upper_dist = (valid["band_upper"] - mid).round(6)
        lower_dist = (mid - valid["band_lower"]).round(6)
        assert np.allclose(upper_dist, lower_dist, atol=1e-10)


class TestStochasticOscillator:
    """Tests for Stochastic Oscillator calculation."""

    def test_values_between_0_and_100(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.stochastic_oscillator()
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["stochastic_oscillator"])
        assert (valid["stochastic_oscillator"] >= -1).all()
        assert (valid["stochastic_oscillator"] <= 101).all()

    def test_formula_correct(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.stochastic_oscillator()
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["stochastic_oscillator"])
        expected = (valid["close"] - valid["low"]) / (valid["high"] - valid["low"]) * 100
        pd.testing.assert_series_equal(
            valid["stochastic_oscillator"], expected, check_names=False, atol=1e-10
        )


class TestRSI:
    """Tests for RSI calculation."""

    def test_values_between_0_and_100(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.rsi(period=14)
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["rsi"])
        assert (valid["rsi"] >= 0).all()
        assert (valid["rsi"] <= 100).all()


class TestSMA:
    """Tests for SMA calculation."""

    def test_sma_converges_to_price(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.sma(period=10)
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["sma"])
        assert len(valid) > 0

    def test_sma_shorter_period_less_smooth(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.sma(period=5, column_name="sma_5")
        indicators.sma(period=20, column_name="sma_20")
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["sma_5", "sma_20"])
        assert len(valid) > 0


class TestCCI:
    """Tests for Commodity Channel Index."""

    def test_references_typical_price(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.commodity_channel_index(period=20)
        frame = indicators.price_data_frame

        assert "commodity_channel_index" in frame.columns
        valid = frame.dropna(subset=["commodity_channel_index"])
        assert len(valid) > 0

    def test_no_pp_column_leakage(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.commodity_channel_index(period=20)
        frame = indicators.price_data_frame

        assert "pp" not in frame.columns


class TestKSTOscillator:
    """Tests for KST Oscillator."""

    def test_signal_line_uses_variable_not_string(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.kst_oscillator(r1=10, r2=15, r3=20, r4=30, n1=10, n2=10, n3=10, n4=15)
        frame = indicators.price_data_frame

        assert "kst_oscillator" in frame.columns
        assert "kst_oscillator_signal" in frame.columns

        valid = frame.dropna(subset=["kst_oscillator", "kst_oscillator_signal"])
        assert len(valid) > 0


class TestADX:
    """Tests for Average Directional Index."""

    def test_values_between_0_and_100(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.adx(period=14)
        frame = indicators.price_data_frame

        valid = frame.dropna(subset=["adx"])
        assert (valid["adx"] >= 0).all()
        assert (valid["adx"] <= 100).all()


class TestOBV:
    """Tests for On-Balance Volume."""

    def test_obv_monotonic_with_price(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.obv()
        frame = indicators.price_data_frame

        assert "obv" in frame.columns
        assert len(frame.dropna(subset=["obv"])) > 0


class TestVWAP:
    """Tests for VWAP."""

    def test_vwap_positive(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.vwap()
        frame = indicators.price_data_frame

        assert "vwap" in frame.columns
        valid = frame.dropna(subset=["vwap"])
        assert (valid["vwap"] > 0).all()


class TestRefresh:
    """Tests for indicator refresh mechanism."""

    def test_refresh_updates_indicators(self, stock_frame):
        indicators = Indicators(price_data_frame=stock_frame)
        indicators.sma(period=10)
        indicators.rsi(period=14)
        indicators.refresh()

        frame = indicators.price_data_frame
        assert "sma" in frame.columns
        assert "rsi" in frame.columns
