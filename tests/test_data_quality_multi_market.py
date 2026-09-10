"""Tests for the multi-market data layer (Wave 1).

Covers DataProviderRegistry, MetalsProvider, CryptoProvider, and quality
validation for metals/crypto data.
"""

import math
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from pyrobot.data.base import Candle, MarketDataProvider, Quote
from pyrobot.data.quality import DataQualityEngine
from pyrobot.data.registry import DataProviderRegistry, get_market_from_env

# ── Synthetic data helpers ────────────────────────────────────────────────────


def _make_metal_frame(symbol: str = "GC=F", n_rows: int = 500) -> pd.DataFrame:
    """Deterministic gold-like daily data with uptrend."""
    base_price = 1800.0
    rows = []
    for i in range(n_rows):
        drift = 0.0003 * i
        cyc = 30 * math.sin(i / 30)
        close = base_price * (1 + drift) + cyc
        rows.append({
            "open": close * 0.998,
            "high": close * 1.012,
            "low": close * 0.990,
            "close": close,
            "volume": 50_000.0 + i * 100,
            "symbol": symbol,
        })
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2021-01-01", periods=n_rows, freq="D", tz="UTC")
    df.index.name = "datetime"
    return df


def _make_crypto_frame(symbol: str = "BTC-USD", n_rows: int = 500) -> pd.DataFrame:
    """Deterministic bitcoin-like daily data with high volatility."""
    base_price = 30000.0
    rows = []
    for i in range(n_rows):
        drift = 0.001 * i
        cyc = 2000 * math.sin(i / 20)
        close = base_price * (1 + drift) + cyc
        rows.append({
            "open": close * 0.995,
            "high": close * 1.04,
            "low": close * 0.97,
            "close": close,
            "volume": 10_000_000.0 + i * 50_000,
            "symbol": symbol,
        })
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2021-01-01", periods=n_rows, freq="D", tz="UTC")
    df.index.name = "datetime"
    return df


# ── Registry tests ────────────────────────────────────────────────────────────


class TestDataProviderRegistry:
    def setup_method(self):
        DataProviderRegistry.clear()

    def test_register_and_create(self):
        DataProviderRegistry.register("us", MarketDataProvider)
        assert "us" in DataProviderRegistry.available()

    def test_create_unknown_market_raises(self):
        with pytest.raises(ValueError, match="No data provider registered"):
            DataProviderRegistry.create("nonexistent")

    def test_register_non_subclass_raises(self):
        with pytest.raises(TypeError):
            DataProviderRegistry.register("bad", str)

    def test_get_class(self):
        DataProviderRegistry.register("metals", MarketDataProvider)
        cls = DataProviderRegistry.get_class("metals")
        assert cls is MarketDataProvider

    def test_clear(self):
        DataProviderRegistry.register("test", MarketDataProvider)
        assert "test" in DataProviderRegistry.available()
        DataProviderRegistry.clear()
        assert DataProviderRegistry.available() == []

    def test_market_from_env_default(self):
        assert get_market_from_env() == "us"

    def test_market_from_env_override(self, monkeypatch):
        monkeypatch.setenv("PYROBOT_MARKET", "metals")
        assert get_market_from_env() == "metals"


# ── MetalsProvider tests ─────────────────────────────────────────────────────


class TestMetalsProvider:
    @patch("pyrobot.data.metals_provider.MetalsProvider._download")
    def test_download_all_returns_frames(self, mock_download, tmp_path):
        mock_download.return_value = _make_metal_frame("GC=F", 100)
        from pyrobot.data.metals_provider import MetalsProvider

        provider = MetalsProvider(symbols=["GC=F"], years=1, data_dir=tmp_path)
        frames = provider.download_all()
        assert "GC=F" in frames
        assert len(frames["GC=F"]) == 100

    @patch("pyrobot.data.metals_provider.MetalsProvider._download")
    def test_get_historical_candles(self, mock_download, tmp_path):
        mock_download.return_value = _make_metal_frame("GC=F", 100)
        from pyrobot.data.metals_provider import MetalsProvider

        provider = MetalsProvider(symbols=["GC=F"], years=1, data_dir=tmp_path)
        start = datetime(2021, 1, 1, tzinfo=timezone.utc)
        end = datetime(2021, 2, 1, tzinfo=timezone.utc)
        candles = provider.get_historical_candles("GC=F", start, end)
        assert len(candles) > 0
        assert all(isinstance(c, Candle) for c in candles)
        assert all(c.symbol == "GC=F" for c in candles)

    @patch("pyrobot.data.metals_provider.MetalsProvider._download")
    def test_get_latest_quote(self, mock_download, tmp_path):
        mock_download.return_value = _make_metal_frame("GC=F", 100)
        from pyrobot.data.metals_provider import MetalsProvider

        provider = MetalsProvider(symbols=["GC=F"], years=1, data_dir=tmp_path)
        quote = provider.get_latest_quote("GC=F")
        assert isinstance(quote, Quote)
        assert quote.symbol == "GC=F"
        assert quote.last_price > 0

    @patch("pyrobot.data.metals_provider.MetalsProvider._download")
    def test_quality_engine_on_metals_data(self, mock_download, tmp_path):
        mock_download.return_value = _make_metal_frame("GC=F", 200)
        from pyrobot.data.metals_provider import MetalsProvider

        provider = MetalsProvider(symbols=["GC=F"], years=1, data_dir=tmp_path)
        frames = provider.download_all()
        df = frames["GC=F"]

        engine = DataQualityEngine()
        report = engine.validate_candles(df.reset_index().to_dict("records"))
        assert report.total_records > 0
        assert report.quality_score > 0.9  # synthetic data should be very clean


# ── CryptoProvider tests ─────────────────────────────────────────────────────


class TestCryptoProvider:
    @patch("pyrobot.data.crypto_provider.CryptoProvider._download")
    def test_download_all_returns_frames(self, mock_download, tmp_path):
        mock_download.return_value = _make_crypto_frame("BTC-USD", 100)
        from pyrobot.data.crypto_provider import CryptoProvider

        provider = CryptoProvider(symbols=["BTC-USD"], years=1, data_dir=tmp_path)
        frames = provider.download_all()
        assert "BTC-USD" in frames
        assert len(frames["BTC-USD"]) == 100

    @patch("pyrobot.data.crypto_provider.CryptoProvider._download")
    def test_get_historical_candles(self, mock_download, tmp_path):
        mock_download.return_value = _make_crypto_frame("BTC-USD", 100)
        from pyrobot.data.crypto_provider import CryptoProvider

        provider = CryptoProvider(symbols=["BTC-USD"], years=1, data_dir=tmp_path)
        start = datetime(2021, 1, 1, tzinfo=timezone.utc)
        end = datetime(2021, 2, 1, tzinfo=timezone.utc)
        candles = provider.get_historical_candles("BTC-USD", start, end)
        assert len(candles) > 0
        assert all(isinstance(c, Candle) for c in candles)
        assert all(c.symbol == "BTC-USD" for c in candles)

    @patch("pyrobot.data.crypto_provider.CryptoProvider._download")
    def test_get_latest_quote(self, mock_download, tmp_path):
        mock_download.return_value = _make_crypto_frame("BTC-USD", 100)
        from pyrobot.data.crypto_provider import CryptoProvider

        provider = CryptoProvider(symbols=["BTC-USD"], years=1, data_dir=tmp_path)
        quote = provider.get_latest_quote("BTC-USD")
        assert isinstance(quote, Quote)
        assert quote.symbol == "BTC-USD"
        assert quote.last_price > 0

    @patch("pyrobot.data.crypto_provider.CryptoProvider._download")
    def test_quality_engine_on_crypto_data(self, mock_download, tmp_path):
        mock_download.return_value = _make_crypto_frame("BTC-USD", 200)
        from pyrobot.data.crypto_provider import CryptoProvider

        provider = CryptoProvider(symbols=["BTC-USD"], years=1, data_dir=tmp_path)
        frames = provider.download_all()
        df = frames["BTC-USD"]

        engine = DataQualityEngine()
        report = engine.validate_candles(df.reset_index().to_dict("records"))
        assert report.total_records > 0
        assert report.quality_score > 0.9

    def test_trading_calendar_24_7(self):
        from pyrobot.data.crypto_provider import TRADING_CALENDAR

        assert TRADING_CALENDAR["name"] == "Crypto_24_7"
        assert "24" in TRADING_CALENDAR["hours"]
        assert "Never" in TRADING_CALENDAR["closed"]


# ── Integration: provider creation via registry ───────────────────────────────


class TestRegistryIntegration:
    def setup_method(self):
        DataProviderRegistry.clear()

    @patch("pyrobot.data.metals_provider.MetalsProvider._download")
    def test_create_metals_via_registry(self, mock_download):
        mock_download.return_value = _make_metal_frame("GC=F", 50)
        from pyrobot.data.metals_provider import MetalsProvider

        DataProviderRegistry.register("metals", MetalsProvider)
        provider = DataProviderRegistry.create("metals", symbols=["GC=F"], years=1)
        assert isinstance(provider, MetalsProvider)

    @patch("pyrobot.data.crypto_provider.CryptoProvider._download")
    def test_create_crypto_via_registry(self, mock_download):
        mock_download.return_value = _make_crypto_frame("BTC-USD", 50)
        from pyrobot.data.crypto_provider import CryptoProvider

        DataProviderRegistry.register("crypto", CryptoProvider)
        provider = DataProviderRegistry.create("crypto", symbols=["BTC-USD"], years=1)
        assert isinstance(provider, CryptoProvider)
