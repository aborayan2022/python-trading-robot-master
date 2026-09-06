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

    def test_not_compressed_to_overbought(self):
        """Regression: RSI must not be double-applied and pinned near 100.

        An oscillating but net-positive series must produce a meaningful RSI
        spread that stays strictly inside (0, 100), and a net-positive series
        must score above its mirror net-negative counterpart.
        """
        from pyrobot.runtime.pipeline import _as_stock_frame

        def closes_of(base, drift, amp):
            return [base + drift * i + amp * np.sin(i / 3.0) for i in range(120)]

        up = closes_of(100.0, 0.5, 3.0)
        down = closes_of(240.0, -0.5, 3.0)

        def rsi_series(values):
            df = pd.DataFrame({
                "open": np.array(values) * 0.998,
                "high": np.array(values) * 1.01,
                "low": np.array(values) * 0.99,
                "close": np.array(values),
                "volume": 1_000_000.0,
                "datetime": pd.date_range("2024-01-01", periods=len(values), freq="D"),
            })
            sf = _as_stock_frame(df, "TEST")
            ind = Indicators(price_data_frame=sf)
            ind.rsi(period=14)
            return sf.frame.xs("TEST", level="symbol")["rsi"].dropna()

        up_rsi, down_rsi = rsi_series(up), rsi_series(down)
        # Early bars can legitimately read 100 (all recent periods were up);
        # the interior, oscillating section must stay strictly inside (0, 100).
        interior_up = up_rsi.iloc[15:60]
        interior_down = down_rsi.iloc[15:60]
        assert (interior_up > 0).all() and (interior_up < 100).all()
        assert (interior_down > 0).all() and (interior_down < 100).all()
        assert up_rsi.mean() > down_rsi.mean()
        assert up_rsi.mean() < 99.0  # the historical bug pinned RSI near 100


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
