"""Wave-5 strategy tests: direction-aware fills, sync_positions, e2e trades.

Mirrors the ``tests/test_us_trend_strategy.py`` pattern but covers the six
new LONG+SHORT strategies. Also includes an end-to-end run through the real
TradingPipeline that asserts *trades* happened (not merely ``bars_processed``),
including a short round-trip that must close via BUY_TO_COVER.
"""

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.data.sectors import (
    MARKET_RISK_LIMITS,
    build_sector_map,
    market_for_symbol,
    risk_limits_for_symbols,
    sector,
)
from pyrobot.runtime.loop import TradingLoop, build_default_pipeline, replay_provider
from pyrobot.runtime.pipeline import _as_stock_frame
from pyrobot.strategies.crypto_mean_rev import CryptoMeanReversionStrategy
from pyrobot.strategies.crypto_trend import CryptoTrendBreakoutStrategy
from pyrobot.strategies.metals_momentum import MetalsMomentumBreakout
from pyrobot.strategies.metals_trend import MetalsTrendFollowStrategy
from pyrobot.strategies.us_breakout import USBreakoutStrategy
from pyrobot.strategies.us_mean_reversion import USMeanReversionStrategy

WAVE5_STRATEGIES = [
    CryptoTrendBreakoutStrategy,
    CryptoMeanReversionStrategy,
    MetalsTrendFollowStrategy,
    MetalsMomentumBreakout,
    USBreakoutStrategy,
    USMeanReversionStrategy,
]


def _bars(prices, day0, symbol="BTC-USD", volume=1_000_000.0):
    bars = []
    for i, close in enumerate(prices):
        ts = day0 + timedelta(days=i)
        bars.append({
            "open": close * 0.998,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
            "datetime": ts,
        })
    return bars


def _frame(bars, symbol="BTC-USD"):
    df = pd.DataFrame(bars)
    df["symbol"] = symbol
    return _as_stock_frame(df, symbol)


def _down_path(n=420, drift=-0.006, amplitude=6.0, period=12.0):
    """Deterministic downtrend with cyclical bounces."""
    return [
        120.0 * (1 + drift * i) + amplitude * math.sin(i / period)
        for i in range(n)
    ]


@pytest.fixture(params=WAVE5_STRATEGIES)
def strategy(request):
    cls = request.param
    return cls(strategy_id=f"{cls.__name__}_test", symbols=["SYM"])


class TestDirectionAwareFills:
    """SELL_SHORT opens a short, BUY_TO_COVER closes it — for every strategy."""

    def test_sell_short_sets_short_holding(self, strategy):
        assert strategy.get_holding("SYM") is False
        strategy.on_order_fill({"symbol": "SYM", "quantity": 10, "side": "SELL_SHORT"})
        assert strategy.get_holding("SYM") is True
        assert strategy._holding_direction.get("SYM") == "short"

    def test_buy_to_cover_clears_short(self, strategy):
        strategy._holding["SYM"] = True
        strategy._holding_direction["SYM"] = "short"
        strategy.on_order_fill({"symbol": "SYM", "quantity": 10, "side": "BUY_TO_COVER"})
        assert strategy.get_holding("SYM") is False
        assert strategy._holding_direction.get("SYM") == "flat"

    def test_buy_sets_long_and_sell_clears(self, strategy):
        strategy.on_order_fill({"symbol": "SYM", "quantity": 10, "side": "BUY"})
        assert strategy.get_holding("SYM") is True
        assert strategy._holding_direction.get("SYM") == "long"
        strategy.on_order_fill({"symbol": "SYM", "quantity": 10, "side": "SELL"})
        assert strategy.get_holding("SYM") is False
        assert strategy._holding_direction.get("SYM") == "flat"


class TestSyncPositions:
    """Cross-session position synchronization (long/short/flat)."""

    def test_sync_long(self, strategy):
        strategy.sync_positions({"SYM": 5.0})
        assert strategy.get_holding("SYM") is True
        assert strategy._holding_direction.get("SYM") == "long"

    def test_sync_short(self, strategy):
        strategy.sync_positions({"SYM": -5.0})
        assert strategy.get_holding("SYM") is True
        assert strategy._holding_direction.get("SYM") == "short"

    def test_sync_flat_clears_state(self, strategy):
        strategy._holding["SYM"] = True
        strategy._holding_direction["SYM"] = "long"
        if hasattr(strategy, "_highest_since_entry"):
            strategy._highest_since_entry["SYM"] = 999.0
            strategy._lowest_since_entry["SYM"] = 1.0
        elif hasattr(strategy, "_entry_high"):
            strategy._entry_high["SYM"] = 999.0
            strategy._entry_low["SYM"] = 1.0
        else:
            strategy._entry_price["SYM"] = 999.0
        strategy.sync_positions({"SYM": 0.0})
        assert strategy.get_holding("SYM") is False
        assert strategy._holding_direction.get("SYM") == "flat"

    def test_sync_missing_symbol_ignored(self, strategy):
        strategy.sync_positions({"OTHER": 10.0})
        assert strategy.get_holding("SYM") is False


class TestCryptoTrendE2EShort:
    """End-to-end: a short that actually opens AND closes through the pipeline.

    Verifies real execution (fills of SELL_SHORT then BUY_TO_COVER) rather than
    only counting processed bars.
    """

    def test_short_round_trip_executes_a_real_trade(self):
        # Deterministic path: warm plateau → rally → a single high-range crash
        # bar (close well below the prior lookback low, below the EMA) that must
        # print SELL_SHORT, then a flat tail so the time stop (max_holding_days)
        # closes it via BUY_TO_COVER. volume_mult < 1 lets the constant volume
        # pass so the test isolates the breakout/time-stop path.
        plateau = [100.0] * 100
        rally = [100.0 + i for i in range(60)]                # → 160
        crash = [
            {"open": 158.0, "high": 159.0, "low": 70.0, "close": 75.0,
             "volume": 1_000_000.0, "datetime": None},
        ]
        tail = [75.0] * 25
        bars = _bars(plateau + rally, datetime(2022, 1, 1, tzinfo=timezone.utc))
        crash[0]["datetime"] = bars[-1]["datetime"] + timedelta(days=1)
        tail_bars = _bars(tail, bars[-1]["datetime"] + timedelta(days=2))
        replays = [{"BTC-USD": bar} for bar in (bars + crash + tail_bars)]

        strategy = CryptoTrendBreakoutStrategy(
            strategy_id="crypto_trend_sht", symbols=["BTC-USD"],
            parameters={"volume_mult": 0.9, "max_holding_days": 8},
        )
        pipeline = build_default_pipeline(
            symbols=["BTC-USD"], initial_balance=100_000.0, strategy=strategy
        )
        loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(replays), bar_interval=0.0)
        result = loop.run()
        assert result["bars_processed"] >= 160  # sanity — the suite must drive bars

        orders = pipeline.order_manager.all_orders()
        filled = [o for o in orders if o.status.value == "FILLED"]
        shorts = [o for o in filled if o.side.value == "SELL_SHORT"]
        covers = [o for o in filled if o.side.value == "BUY_TO_COVER"]
        assert shorts, "a SELL_SHORT must be filled, not just signals generated"
        assert covers, "the short must be closed by a BUY_TO_COVER fill"
        # The strategy must believe it is flat after the round trip.
        assert strategy.get_holding("BTC-USD") is False
        assert strategy._holding_direction.get("BTC-USD") == "flat"


class TestSectorRiskMaps:
    """Multi-market sector classification and per-market risk limits."""

    def test_metals_classified(self):
        assert sector("GC=F") == "Precious Metals"
        assert sector("SLV") == "Precious Metals"
        assert market_for_symbol("GLD") == "metals"

    def test_crypto_classified(self):
        assert sector("BTC-USD") == "Cryptocurrency"
        assert market_for_symbol("ETH-USD") == "crypto"

    def test_unknown_falls_back(self):
        assert sector("ZZZZ") == "UNKNOWN"
        assert market_for_symbol("ZZZZ") == "unknown"

    def test_crypto_universe_tighter_limits(self):
        limits = risk_limits_for_symbols(["BTC-USD", "ETH-USD"])
        assert limits["max_position_size_pct"] == MARKET_RISK_LIMITS["crypto"]["max_position_size_pct"]
        assert limits["max_position_size_pct"] < MARKET_RISK_LIMITS["US"]["max_position_size_pct"]

    def test_build_sector_map_multi_market(self):
        smap = build_sector_map(["AAPL", "GC=F", "BTC-USD"])
        assert smap == {"AAPL": "Information Technology", "GC=F": "Precious Metals", "BTC-USD": "Cryptocurrency"}

    def test_paper_broker_persistence_round_trip(self, tmp_path):
        path = tmp_path / "paper_state.json"
        broker = PaperBroker(initial_balance=100_000.0)
        broker._positions["AAPL"] = {"symbol": "AAPL", "quantity": 20.0, "average_price": 150.0, "asset_type": "EQUITY"}
        broker._short_positions["BTC-USD"] = {"symbol": "BTC-USD", "quantity": 2.0, "average_price": 60_000.0, "asset_type": "EQUITY"}
        broker._cash_balance = 50_000.0
        broker._realized_pnl = 1_234.5
        broker.save_state(path)

        restored = PaperBroker(initial_balance=10_000.0)
        assert restored.load_state(path) is True
        assert restored._cash_balance == 50_000.0
        assert restored._realized_pnl == 1_234.5
        assert restored._positions["AAPL"]["quantity"] == 20.0
        assert restored._short_positions["BTC-USD"]["quantity"] == 2.0
        # signed position map used by strategy.sync_positions
        pmap = restored.position_map()
        assert pmap["AAPL"] == 20.0
        assert pmap["BTC-USD"] == -2.0

    def test_paper_broker_load_missing_state(self, tmp_path):
        broker = PaperBroker(initial_balance=100_000.0)
        assert broker.load_state(tmp_path / "nope.json") is False
