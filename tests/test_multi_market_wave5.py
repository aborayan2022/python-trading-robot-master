"""Wave-5 strategy tests: direction-aware fills, sync_positions, e2e trades.

Mirrors the ``tests/test_us_trend_strategy.py`` pattern but covers the six
new LONG+SHORT strategies. Also includes an end-to-end run through the real
TradingPipeline that asserts *trades* happened (not merely ``bars_processed``),
including a short round-trip that must close via BUY_TO_COVER.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Dict

import pandas as pd
import pytest

from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.data.sectors import (
    MARKET_RISK_LIMITS,
    build_risk_limits,
    build_sector_map,
    market_for_symbol,
    risk_limits_for_symbols,
    sector,
)
from pyrobot.models.signal import SignalAction
from pyrobot.runtime.loop import TradingLoop, build_default_pipeline, replay_provider
from pyrobot.runtime.pipeline import _as_stock_frame
from pyrobot.strategies.base import BaseStrategy
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


TREND_PAIR = [MetalsMomentumBreakout, CryptoTrendBreakoutStrategy]


def _constant_frame(value, n=130, symbol="SYM"):
    return _frame(_bars([value] * n, datetime(2022, 1, 1, tzinfo=timezone.utc)), symbol)


class TestRatchetStops:
    """P1-a: ATR trailing stops are anchored to the fill price and ratchet
    monotonically off the running high/low, never drifting toward the signal
    close as ATR changes (metals_momentum + crypto_trend)."""

    @pytest.mark.parametrize("cls", TREND_PAIR, ids=lambda c: c.__name__)
    def test_fill_price_recorded_on_entry(self, cls):
        strategy = cls(strategy_id="t", symbols=["SYM"])
        strategy.on_order_fill({"symbol": "SYM", "quantity": 10, "side": "BUY", "fill_price": 151.25})
        assert strategy._entry_price["SYM"] == 151.25
        assert strategy._stop_level == {}
        assert strategy._extreme_high == {}
        assert strategy._extreme_low == {}
        strategy.on_order_fill({"symbol": "SYM", "quantity": 10, "side": "SELL"})
        assert "SYM" not in strategy._entry_price

    @pytest.mark.parametrize("cls", TREND_PAIR, ids=lambda c: c.__name__)
    def test_short_fill_uses_avg_fill_price(self, cls):
        strategy = cls(strategy_id="t", symbols=["SYM"])
        strategy.on_order_fill({"symbol": "SYM", "quantity": 10, "side": "SELL_SHORT", "avg_fill_price": 88.0})
        assert strategy._entry_price["SYM"] == 88.0
        assert strategy._holding_direction["SYM"] == "short"

    @pytest.mark.parametrize("cls", TREND_PAIR, ids=lambda c: c.__name__)
    def test_long_stop_ratchets_up_to_protect_gains(self, cls):
        strategy = cls(
            strategy_id="t", symbols=["SYM"],
            parameters={"max_holding_days": 100},
        )
        # Simulate an open long entered ~100 that then ran to 120: the old
        # fixed entry-anchored stop (~entry - 2*ATR ≈ 95) would NOT exit at
        # 112; the ratcheted stop must.
        strategy._holding["SYM"] = True
        strategy._holding_direction["SYM"] = "long"
        strategy._bar_count["SYM"] = 500
        strategy._entry_bar_idx["SYM"] = 490
        strategy._entry_price["SYM"] = 100.0
        strategy._extreme_high["SYM"] = 120.0
        strategy._stop_level["SYM"] = 115.0

        result_up = strategy._evaluate("SYM", _constant_frame(120.0))
        assert result_up.action == SignalAction.HOLD

        result_drop = strategy._evaluate("SYM", _constant_frame(112.0))
        assert result_drop.action == SignalAction.SELL
        assert "trailing stop" in result_drop.reason.lower()
        assert strategy._stop_level["SYM"] >= 115.0  # never loosened

    @pytest.mark.parametrize("cls", TREND_PAIR, ids=lambda c: c.__name__)
    def test_short_stop_ratchets_down_to_protect_gains(self, cls):
        strategy = cls(
            strategy_id="t", symbols=["SYM"],
            parameters={"max_holding_days": 100},
        )
        # Open short at ~100 that fell to 80: a fixed stop (~entry + 2*ATR ≈
        # 103) would NOT cover at 86; the ratcheted stop must.
        strategy._holding["SYM"] = True
        strategy._holding_direction["SYM"] = "short"
        strategy._bar_count["SYM"] = 500
        strategy._entry_bar_idx["SYM"] = 490
        strategy._entry_price["SYM"] = 100.0
        strategy._extreme_low["SYM"] = 80.0
        strategy._stop_level["SYM"] = 102.0

        result_down = strategy._evaluate("SYM", _constant_frame(80.0))
        assert result_down.action == SignalAction.HOLD

        result_up = strategy._evaluate("SYM", _constant_frame(86.0))
        assert result_up.action == SignalAction.BUY_TO_COVER
        assert "trailing stop" in result_up.reason.lower()
        assert strategy._stop_level["SYM"] <= 102.0  # never loosened


_PLAN: Dict[str, Dict[int, str]] = {}
_STASH: Dict[str, list] = {"fills": []}
_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _reset_script(plan) -> None:
    """Point the scripted strategy at a bar-indexed action schedule."""
    global _PLAN
    _PLAN = {sym: {i: act for i, act in schedule.items() if act != "HOLD"} for sym, schedule in plan.items()}
    _STASH["fills"] = []


class _ScriptedStrategy(BaseStrategy):
    """Strategy that replays a scripted BUY/SELL/SELL_SHORT/BUY_TO_COVER schedule."""

    def __init__(self, strategy_id: str, symbols, parameters=None) -> None:
        super().__init__(strategy_id, symbols, parameters)
        self._idx = {s: 0 for s in symbols}

    def initialize(self) -> None:
        pass

    def on_bar(self, symbol, bar, stock_frame):
        from pyrobot.models.signal import Signal, SignalAction

        i = self._idx.get(symbol, 0)
        self._idx[symbol] = i + 1
        action = _PLAN.get(symbol, {}).get(i, "HOLD")
        return Signal(symbol=symbol, action=SignalAction[action], strategy_id=self._strategy_id, reason="scripted")

    def on_order_fill(self, order_dict) -> None:
        _STASH["fills"].append({
            "symbol": order_dict["symbol"],
            "quantity": order_dict["quantity"],
            "side": order_dict["side"],
        })


class TestBacktestRunnerAccounting:
    """Direct tests of MultiMarketBacktest honest short/long accounting.

    The reviewer flagged that ``runner.py`` had no direct tests (short
    round-trip PnL, per-bar borrow costs, partial-fill re-queueing, benchmark
    buying each symbol at its own first bar). These drive the runner with a
    scripted strategy and a zero-fee cost model so accounting can be checked
    to the cent.
    """

    def _runner(self, tmp_path, plan, prices, *, volume=1_000_000.0, borrow_rate=1.0,
                participation=1.0, commission=0.0, min_commission=0.0, sec_fee=0.0):
        from pyrobot.backtesting.cost_model import CostModelConfig, ExecutionCostModel
        from pyrobot.backtesting.runner import MultiMarketBacktest

        _reset_script(plan)
        idx = pd.date_range("2024-01-01", periods=len(prices), freq="D", tz="UTC")
        frame = pd.DataFrame(
            {"open": prices, "high": prices, "low": prices, "close": prices,
             "volume": [float(volume)] * len(prices)}, index=idx)
        frames = {"SYM": frame}
        config = CostModelConfig(
            commission_per_share=commission, min_commission=min_commission,
            sec_fee_rate=sec_fee, half_spread_bps=0.0, base_slippage_bps=0.0,
            market_impact_coefficient=0.0, max_volume_participation=participation,
            borrow_annual_rate_pct=borrow_rate,
        )
        runner = MultiMarketBacktest(
            strategy_class=_ScriptedStrategy, strategy_name="scripted",
            symbols=["SYM"], data_dir=tmp_path, initial_balance=100_000.0,
            cost_model=ExecutionCostModel(config=config),
        )
        return runner, frames

    def test_long_round_trip_pnl_and_fees(self, tmp_path):
        runner, frames = self._runner(tmp_path, {"SYM": {0: "BUY", 1: "SELL"}},
                                      [100.0] * 3, commission=0.01)
        result = runner.honest_backtest(frames)
        trade = result["trades"][0]
        assert trade["quantity"] == 120          # 12% of $100k at $100
        assert trade["fees"] > 0.0               # entry + exit commissions booked
        assert trade["entry_ts"] == "2024-01-02 00:00:00+00:00"  # BUY fills at next bar's open
        assert trade["exit_ts"].startswith("2024-01-03")
        assert result["summary"]["total_trades"] == 1

    def test_short_round_trip_includes_borrow_cost(self, tmp_path):
        runner, frames = self._runner(
            tmp_path, {"SYM": {0: "SELL_SHORT", 1: "BUY_TO_COVER"}}, [100.0] * 3, borrow_rate=5.0)
        result = runner.honest_backtest(frames)
        trade = result["trades"][0]
        assert trade["side"] == "BUY_TO_COVER"
        assert trade["quantity"] == 120
        # Flat price → gross PnL 0; only borrow (and zero fees) remain. The
        # short is open for exactly one bar charge (bar0, after its fill), then
        # covered at bar1 before the borrow loop runs again.
        assert result["estimated_borrow_cost_usd"] > 0.0
        expected_borrow = 12_000.0 * 0.05 / 252
        assert result["estimated_borrow_cost_usd"] == pytest.approx(expected_borrow, abs=0.05)
        assert result["summary"]["ending_balance"] == pytest.approx(100_000.0 - expected_borrow, abs=0.5)

    def test_partial_fill_requeued_next_bar(self, tmp_path):
        # bar1 fills 50/120 (5% of a 1000-volume bar); the 70 remainder requeues
        # and fully fills at bar2 against a 10000-volume bar; bar4 SELL closes.
        volumes = [1_000_000.0, 1_000.0, 10_000.0, 1_000_000.0, 1_000_000.0]
        runner, frames = self._runner(
            tmp_path, {"SYM": {0: "BUY", 3: "SELL"}}, [100.0] * 5, volume=volumes[0],
            participation=0.05)
        frames["SYM"]["volume"] = volumes  # override per-bar
        result = runner.honest_backtest(frames)
        fills = [(f["side"], f["quantity"]) for f in _STASH["fills"]]
        assert fills == [("BUY", 50.0), ("BUY", 70.0), ("SELL", 120.0)]
        assert result["summary"]["total_trades"] == 1
        assert result["trades"][0]["quantity"] == 120

    def test_benchmark_buys_each_symbol_at_own_first_bar(self, tmp_path):
        from pyrobot.backtesting.cost_model import CostModelConfig, ExecutionCostModel
        from pyrobot.backtesting.runner import MultiMarketBacktest

        idx_a = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
        idx_b = pd.date_range("2024-02-01", periods=2, freq="D", tz="UTC")
        frames = {
            "EARLY": pd.DataFrame(
                {"open": [100, 101, 102], "high": [100, 101, 102], "low": [100, 101, 102],
                 "close": [100, 101, 102], "volume": [1e6] * 3}, index=idx_a),
            "LATE": pd.DataFrame(
                {"open": [50, 51], "high": [50, 51], "low": [50, 51],
                 "close": [50, 51], "volume": [1e6] * 2}, index=idx_b),
        }
        config = CostModelConfig(commission_per_share=0.0, min_commission=0.0,
                                 sec_fee_rate=0.0, half_spread_bps=0.0,
                                 base_slippage_bps=0.0, market_impact_coefficient=0.0)
        runner = MultiMarketBacktest(
            strategy_class=_ScriptedStrategy, strategy_name="scripted",
            symbols=["EARLY", "LATE"], data_dir=tmp_path, initial_balance=100_000.0,
            cost_model=ExecutionCostModel(config=config),
        )
        bench = runner.buy_and_hold_benchmark(frames)
        # EARLY: 500 sh @ 100 = $50,000; LATE: 1,000 sh @ 50 = $50,000; final
        # close EARLY 102, LATE 51 → ending equity ≈ 500*102 + 1000*51 = $102,000.
        # If LATE were skipped (later listing) the balance would stay ~$101,000.
        assert bench["equity_curve"]
        assert bench["equity_curve"][-1]["equity"] == pytest.approx(102_000.0, abs=100.0)

    def test_partial_scaling_accumulates_entry_fees(self, tmp_path):
        # Signals can only open/close, so drive the accounting engine (_fill)
        # directly: BUY 60, BUY-add 60, then SELL the full 120. Both entries
        # must pay commission and the exit trade must book all three fees.
        from pyrobot.backtesting.runner import _fill

        runner, _ = self._runner(
            tmp_path, {"SYM": {}}, [100.0] * 3, commission=0.01, volume=1_000_000.0)
        cost_model = runner.cost_model
        positions: Dict[str, Dict[str, float]] = {}
        entry_fees: Dict[str, float] = {}
        trades: list = []
        still: list = []
        strategy = _ScriptedStrategy("x", ["SYM"])
        _reset_script({"SYM": {}})
        row = {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1e6}
        cash = 100_000.0
        cash = _fill({"symbol": "SYM", "side": "BUY", "quantity": 60}, row, cost_model,
                     cash, positions, entry_fees, trades, still, _dt, strategy)
        cash = _fill({"symbol": "SYM", "side": "BUY", "quantity": 60}, row, cost_model,
                     cash, positions, entry_fees, trades, still, _dt, strategy)
        assert positions["SYM"]["quantity"] == 120
        assert entry_fees["SYM"] == pytest.approx(60 * 0.01 + 60 * 0.01, rel=0.05)
        cash = _fill({"symbol": "SYM", "side": "SELL", "quantity": 120}, row, cost_model,
                     cash, positions, entry_fees, trades, still, _dt, strategy)
        trade = trades[0]
        per_fill_comm = 60 * 0.01
        assert entry_fees.get("SYM") is None  # consumed on close
        assert trade["fees"] == pytest.approx(per_fill_comm * 4, rel=0.05)  # 2 entries + 1 exit
        assert trade["pnl"] == pytest.approx(-per_fill_comm * 4, rel=0.05)


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

    def test_build_risk_limits_reflects_market(self):
        crypto_limits = build_risk_limits(["BTC-USD", "ETH-USD"])
        assert crypto_limits.max_position_size_pct == MARKET_RISK_LIMITS["crypto"]["max_position_size_pct"]
        assert crypto_limits.max_sector_concentration_pct == MARKET_RISK_LIMITS["crypto"]["max_sector_exposure_pct"]
        metals_limits = build_risk_limits(["GC=F", "SI=F"])
        assert metals_limits.max_position_size_pct == MARKET_RISK_LIMITS["metals"]["max_position_size_pct"]

    def test_crypto_universe_none_dead_limit(self, tmp_path):
        # P1-c: a crypto pipeline built for the session must carry an effective
        # sector map AND per-market limits (position size + sector cap).
        pipeline = build_default_pipeline(
            symbols=["BTC-USD", "ETH-USD"], initial_balance=100_000.0,
            sector_map=build_sector_map(["BTC-USD", "ETH-USD"]),
            risk_limits=build_risk_limits(["BTC-USD", "ETH-USD"]),
        )
        limits = pipeline.risk_manager.limits
        assert limits.max_position_size_pct == 0.05
        assert limits.max_sector_concentration_pct == 0.10
        exposure = pipeline.risk_manager.exposure_monitor
        assert exposure._sector_map["BTC-USD"] == "Cryptocurrency"
        assert exposure._sector_map["ETH-USD"] == "Cryptocurrency"

    def test_crypto_position_cap_enforced(self):
        # $6,000 on a $100,000 account is 6% > the 5% crypto cap → rejected;
        # $4,000 (4%) still clears. Same-value order is fine for US (12% cap).
        from pyrobot.models.order import Order, OrderSide

        def approved(market, syms, qty):
            pip = build_default_pipeline(
                symbols=syms, initial_balance=100_000.0,
                sector_map=build_sector_map(syms), risk_limits=build_risk_limits(syms),
            )
            order = Order(client_order_id="t", symbol=syms[0], quantity=qty,
                          order_type="MARKET", side=OrderSide.BUY)
            ok, _ = pip.risk_manager.check_order(
                order=order, positions={}, prices={syms[0]: 100.0}, equity=100_000.0)
            return ok

        assert approved("crypto", ["BTC-USD"], 60) is False
        assert approved("crypto", ["BTC-USD"], 40) is True
        assert approved("US", ["AAPL"], 130) is False
        assert approved("US", ["AAPL"], 100) is True

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
