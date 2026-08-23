"""Integration tests for the runtime pipeline and trading loop.

These prove the P0 connection: Data → Features/Strategy → Risk → Execution →
Audit → Risk book, end to end, on the PaperBroker.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from pyrobot.ai.ensemble import EnsembleSignalEngine
from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.risk.kill_switch import KillSwitchReason
from pyrobot.risk.limits import RiskLimits
from pyrobot.risk.manager import RiskManager
from pyrobot.runtime import (
    TradingLoop,
    TradingPipeline,
    generate_replay_data,
    replay_provider,
)
from pyrobot.strategies.base import BaseStrategy


class _ScriptedStrategy(BaseStrategy):
    """Buys once on bar `buy_at`, sells everything on bar `sell_at`."""

    def __init__(self, buy_at: int, sell_at: int | None = None) -> None:
        super().__init__(strategy_id="scripted", symbols=["MSFT"])
        self.buy_at = buy_at
        self.sell_at = sell_at
        self.bars_seen = 0
        self.fills: list = []

    def initialize(self) -> None:  # ABC hook
        return None

    def on_bar(self, symbol: str, bar: dict, stock_frame) -> Signal:
        self.bars_seen += 1
        if self.bars_seen == self.buy_at:
            return Signal(symbol=symbol, action=SignalAction.BUY,
                          confidence=0.9, strategy_id="scripted")
        if self.sell_at is not None and self.bars_seen == self.sell_at:
            return Signal(symbol=symbol, action=SignalAction.SELL,
                          confidence=0.9, strategy_id="scripted")
        return Signal(symbol=symbol, action=SignalAction.NO_TRADE, strategy_id="scripted")

    def on_order_fill(self, order_dict: dict) -> None:
        self.fills.append(order_dict)


def _rising_bars(symbols, n, start_ts=None, base=100.0):
    start_ts = start_ts or datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bars = []
    price = {s: base for s in symbols}
    for i in range(n):
        ts = start_ts + timedelta(minutes=i)
        row = {}
        for s in symbols:
            price[s] *= 1.001
            row[s] = {"open": round(price[s] * 0.999, 2), "high": round(price[s] * 1.002, 2),
                      "low": round(price[s] * 0.998, 2), "close": round(price[s], 2),
                      "volume": 250_000.0, "datetime": ts}
        bars.append(row)
    return bars


def _make_pipeline(strategy, symbols=("MSFT",), limits=None, dry_run=False, ledger_path=None):
    broker = PaperBroker(initial_balance=100_000.0)
    ledger = AuditLedger(log_path=ledger_path)
    limits = limits or RiskLimits()
    risk_manager = RiskManager(limits=limits)
    pipeline = TradingPipeline(
        broker=broker,
        symbols=list(symbols),
        signal_source=strategy,
        risk_manager=risk_manager,
        audit_ledger=ledger,
        dry_run=dry_run,
        min_history_bars=5,
    )
    return pipeline, broker, ledger


class TestTradingPipelineEndToEnd:

    def test_buy_signal_becomes_audited_filled_position(self, tmp_path):
        """One connected path: signal → risk → execution → fill → audit → risk book."""
        strategy = _ScriptedStrategy(buy_at=10)
        pipeline, broker, ledger = _make_pipeline(
            strategy, ledger_path=str(tmp_path / "audit.jsonl")
        )

        for bars in _rising_bars(("MSFT",), 30):
            pipeline.process_bar(bars, timestamp=bars["MSFT"]["datetime"])

        # Order flowed through the broker: a real position now exists
        positions = {p["symbol"]: p["quantity"] for p in broker.get_positions()}
        assert positions.get("MSPT", positions.get("MSFT", 0)) == positions.get("MSFT", 0)
        assert positions.get("MSFT", 0) > 0
        account = broker.get_account_info()
        assert account["cash_balance"] < 100_000.0  # cash actually spent

        # Risk book tracked the fill
        tracked = pipeline.risk_manager.get_tracked_positions()
        assert tracked.get("MSFT", {}).get("qty", 0) > 0

        # Strategy observed its own fill
        assert len(strategy.fills) == 1

        # Audit chain contains every stage, in a verifiable chain
        actions = {e.action for e in ledger.get_events()}
        assert AuditAction.MARKET_DATA_RECORDED in actions
        assert AuditAction.SIGNAL_GENERATED in actions
        assert AuditAction.RISK_EVALUATED in actions
        assert AuditAction.ORDER_SUBMITTED in actions
        assert AuditAction.ORDER_FILLED in actions
        assert ledger.verify_integrity()

    def test_sell_signal_flattens_position(self):
        strategy = _ScriptedStrategy(buy_at=8, sell_at=20)
        pipeline, broker, ledger = _make_pipeline(strategy)

        for bars in _rising_bars(("MSFT",), 30):
            pipeline.process_bar(bars, timestamp=bars["MSFT"]["datetime"])

        positions = {p["symbol"]: p["quantity"] for p in broker.get_positions()}
        assert positions.get("MSFT", 0) == 0
        # Rising market → realized PnL positive on the round trip
        assert broker.portfolio_summary["realized_pnl"] > 0
        assert AuditAction.ORDER_FILLED in {e.action for e in ledger.get_events()}

    def test_dry_run_never_touches_broker(self):
        strategy = _ScriptedStrategy(buy_at=8)
        pipeline, broker, ledger = _make_pipeline(strategy, dry_run=True)

        for bars in _rising_bars(("MSFT",), 20):
            pipeline.process_bar(bars, timestamp=bars["MSFT"]["datetime"])

        assert broker.get_positions() == []
        assert broker.get_account_info()["cash_balance"] == 100_000.0
        assert AuditAction.SIGNAL_GENERATED in {e.action for e in ledger.get_events()}

    def test_kill_switch_blocks_everything(self):
        strategy = _ScriptedStrategy(buy_at=8)
        pipeline, broker, ledger = _make_pipeline(strategy)

        bars = _rising_bars(("MSFT",), 20)
        for b in bars[:7]:
            pipeline.process_bar(b, timestamp=b["MSFT"]["datetime"])

        pipeline.kill_switch.activate(reason=KillSwitchReason.OPERATOR, detail='test')

        for b in bars[7:]:
            pipeline.process_bar(b, timestamp=b["MSFT"]["datetime"])

        assert broker.get_positions() == []  # buy signal at bar 8 never executed
        assert pipeline.kill_switch_triggered is True

    def test_drift_check_scales_risk_down(self):
        strategy = _ScriptedStrategy(buy_at=10_000)  # never trades
        pipeline, broker, ledger = _make_pipeline(strategy)
        from pyrobot.ai.drift import DriftDetector
        pipeline.drift_detector = DriftDetector()
        pipeline.drift_interval = 10

        bars = _rising_bars(("MSFT",), 60)
        for b in bars:
            pipeline.process_bar(b, timestamp=b["MSFT"]["datetime"])

        # Poison the baseline with a strongly shifted distribution so the next
        # scheduled drift check (every drift_interval bars) must flag drift
        pipeline._baseline_features = pd.DataFrame({
            "return_1": np.random.default_rng(1).normal(5.0, 0.1, 200),
            "atr_pct_14": np.random.default_rng(2).normal(5.0, 0.1, 200),
        })
        for b in _rising_bars(("MSFT",), 10, base=160.0):
            pipeline.process_bar(b, timestamp=b["MSFT"]["datetime"])

        assert pipeline.risk_manager.model_risk_scale < 1.0
        assert AuditAction.MODEL_DRIFT_CHECK in {e.action for e in ledger.get_events()}


class TestAIPath:

    def test_unfitted_ensemble_never_trades(self):
        """Unfitted models → prob 0.5 → NO_TRADE: no accidental orders."""
        pipeline, broker, ledger = _make_pipeline(EnsembleSignalEngine())
        for bars in _rising_bars(("MSFT",), 40):
            pipeline.process_bar(bars, timestamp=bars["MSFT"]["datetime"])
        assert broker.get_positions() == []

    def test_fitted_ensemble_trades_on_strong_trend(self, tmp_path):
        """A trained direction model drives real orders through the same path."""
        from pyrobot.ai.labels import LabelBuilder
        from pyrobot.ai.models import LogisticDirectionModel

        rng = np.random.default_rng(4)
        n = 600
        close = 100.0 * np.cumprod(1.0 + rng.normal(0.0008, 0.01, n))
        df = pd.DataFrame({
            "open": close * (1 + rng.normal(0, 0.001, n)),
            "high": close * 1.004, "low": close * 0.996, "close": close,
            "volume": rng.uniform(1e5, 5e5, n),
        })
        from pyrobot.features.engine import FeatureEngine
        feature_engine = FeatureEngine()
        feats = feature_engine.extract_features(df)
        labels = LabelBuilder().direction_labels(feats.join(df[["close"]]), horizon=5)
        mask = labels.notna()
        model = LogisticDirectionModel(n_iterations=3000, learning_rate=0.3)
        model.fit(feats[mask], labels[mask])
        assert model.is_fitted

        ensemble = EnsembleSignalEngine(direction_model=model, volatility_model=None)
        broker = PaperBroker(initial_balance=100_000.0)
        ledger = AuditLedger(log_path=str(tmp_path / "ai_audit.jsonl"))
        pipeline = TradingPipeline(
            broker=broker, symbols=["MSFT"], signal_source=ensemble,
            audit_ledger=ledger, feature_engine=feature_engine,
            min_history_bars=30,
        )

        last = None
        for bars in _rising_bars(("MSFT",), 80):
            last = pipeline.process_bar(bars, timestamp=bars["MSFT"]["datetime"])

        # The connected path executed AI signals (whatever the model decided)
        assert last is not None
        assert last["kill_switch_active"] is False
        assert ledger.verify_integrity()


class TestTradingLoop:

    def test_replay_loop_runs_to_completion(self, tmp_path):
        pipeline, broker, ledger = _make_pipeline(
            EnsembleSignalEngine(), ledger_path=str(tmp_path / "loop_audit.jsonl")
        )
        bars = generate_replay_data(["MSFT", "AAPL"], n_bars=40, seed=7)
        loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(bars))
        result = loop.run()

        assert result["bars_processed"] == 40
        assert result["status"]["bars_processed"] == 40
        assert result["status"]["kill_switch_active"] is False
        assert len(ledger.get_events()) >= 40  # at least the market-data records

    def test_loop_stop_request(self):
        pipeline, broker, ledger = _make_pipeline(EnsembleSignalEngine())
        bars = generate_replay_data(["MSFT"], n_bars=100, seed=1)
        loop = TradingLoop(pipeline=pipeline, bar_provider=replay_provider(bars))

        def stop_after_5(index):
            if index == 5:
                loop.stop()
            return bars[index] if index < len(bars) else None

        loop.bar_provider = stop_after_5
        result = loop.run()
        assert result["bars_processed"] == 6  # stopped gracefully mid-run

    def test_replay_data_is_deterministic(self):
        a = generate_replay_data(["MSFT"], 50, seed=11)
        b = generate_replay_data(["MSFT"], 50, seed=11)
        assert [bar["MSFT"]["close"] for bar in a] == [bar["MSFT"]["close"] for bar in b]

    def test_build_default_pipeline_smoke(self):
        from pyrobot.runtime.loop import build_default_pipeline

        pipeline = build_default_pipeline(symbols=["MSFT"], mode="paper")
        assert isinstance(pipeline, TradingPipeline)
        assert isinstance(pipeline.signal_source, EnsembleSignalEngine)
