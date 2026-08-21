"""Unit tests for the Data Platform (Storage, Versioning, Quality, Feed)."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from pyrobot.data import (
    Candle,
    Quote,
    DataFrequency,
    DataQualityEngine,
    DatasetStore,
    MarketDataFeed,
    MarketDataProvider,
)
from pyrobot.exceptions import StaleDataError


class DummyDataProvider(MarketDataProvider):
    def get_historical_candles(self, symbol, start, end, frequency=DataFrequency.MINUTE_1):
        return []

    def get_latest_quote(self, symbol: str) -> Quote:
        return Quote(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            bid=150.0,
            ask=150.10,
            last_price=150.05,
        )

    def get_quotes(self, symbols):
        return {s: self.get_latest_quote(s) for s in symbols}


class TestDataStorage:
    def test_save_and_load_dataset_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = DatasetStore(base_dir=tmp_dir)

            dates = pd.date_range(start="2026-01-01", periods=10, freq="D", tz="UTC")
            df = pd.DataFrame(
                {
                    "open": np.linspace(100, 110, 10),
                    "high": np.linspace(102, 112, 10),
                    "low": np.linspace(99, 109, 10),
                    "close": np.linspace(101, 111, 10),
                    "volume": [1000] * 10,
                },
                index=dates,
            )

            version = store.save_dataset(df, symbol="AAPL", frequency="1d")
            assert version.symbol == "AAPL"
            assert version.row_count == 10
            assert len(version.checksum) == 64

            loaded_df, loaded_meta = store.load_dataset(version.dataset_id)
            assert len(loaded_df) == 10
            assert loaded_meta.checksum == version.checksum
            assert np.allclose(loaded_df["close"], df["close"])

    def test_list_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = DatasetStore(base_dir=tmp_dir)
            dates = pd.date_range(start="2026-01-01", periods=5, freq="D", tz="UTC")
            df = pd.DataFrame({"close": [100, 101, 102, 103, 104]}, index=dates)

            store.save_dataset(df, symbol="AAPL")
            store.save_dataset(df, symbol="MSFT")

            all_versions = store.list_versions()
            assert len(all_versions) == 2

            aapl_versions = store.list_versions(symbol="AAPL")
            assert len(aapl_versions) == 1
            assert aapl_versions[0].symbol == "AAPL"


class TestDataFeed:
    def test_stale_data_detection(self) -> None:
        provider = DummyDataProvider()
        feed = MarketDataFeed(provider=provider, stale_threshold_seconds=10.0)

        # Update with an old timestamp
        old_time = datetime.now(timezone.utc) - timedelta(seconds=20)
        old_quote = Quote(
            symbol="AAPL",
            timestamp=old_time,
            bid=150.0,
            ask=150.10,
            last_price=150.05,
        )
        feed.update_quote("AAPL", old_quote)

        # Checking staleness should raise StaleDataError
        with pytest.raises(StaleDataError):
            feed.check_staleness("AAPL")

    def test_fresh_data_passes(self) -> None:
        provider = DummyDataProvider()
        feed = MarketDataFeed(provider=provider, stale_threshold_seconds=10.0)

        fresh_quote = Quote(
            symbol="AAPL",
            timestamp=datetime.now(timezone.utc),
            bid=150.0,
            ask=150.10,
            last_price=150.05,
        )
        feed.update_quote("AAPL", fresh_quote)
        feed.check_staleness("AAPL")  # Should not raise
