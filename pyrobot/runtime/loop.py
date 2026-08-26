"""Main trading loop: scheduler, heartbeat, and graceful shutdown.

Run the built-in paper replay demo:

    python -m pyrobot.runtime.loop

Environment:
    PYROBOT_SYMBOLS          comma-separated universe      (default MSFT,AAPL)
    PYROBOT_BARS             number of replay bars          (default 500)
    PYROBOT_SEED             replay RNG seed                (default 7)
    PYROBOT_MODE             paper | dry_run                (default paper)
    PYROBOT_BALANCE          initial cash                   (default 100000)
    PYROBOT_AUDIT_PATH       audit ledger JSONL path        (default data/audit/ledger.jsonl)
    PYROBOT_BAR_INTERVAL     seconds between bars           (default 0 = as fast as possible)

The replay source is synthetic (deterministic random walk) so the loop runs
anywhere with zero external dependencies — for live data, pass a bar provider
callable to TradingLoop (e.g., polling an Alpaca broker for latest quotes).
"""

import os
import signal as os_signal
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from pyrobot.ai.drift import DriftDetector
from pyrobot.ai.ensemble import EnsembleSignalEngine
from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.brokers.alpaca_broker import AlpacaBroker
from pyrobot.brokers.paper_broker import PaperBroker
from pyrobot.data.alpaca import AlpacaDataProvider
from pyrobot.exceptions import StaleDataError
from pyrobot.logging_config import get_logger
from pyrobot.monitoring import RuntimeMetrics
from pyrobot.risk.kill_switch import KillSwitchReason
from pyrobot.risk.limits import RiskLimits
from pyrobot.risk.manager import RiskManager
from pyrobot.runtime.pipeline import TradingPipeline
from pyrobot.strategies.base import BaseStrategy

logger = get_logger("runtime_loop")

BarProvider = Callable[[int], Optional[Dict[str, dict]]]


def generate_replay_data(
    symbols: List[str],
    n_bars: int,
    seed: int = 7,
    start_price: float = 100.0,
    start: Optional[datetime] = None,
) -> List[Dict[str, dict]]:
    """Deterministic synthetic OHLCV bars for every symbol (paper demo data)."""
    rng = np.random.default_rng(seed)
    start = start or datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bars: List[Dict[str, dict]] = []
    prices = {s: start_price * (1.0 + rng.uniform(-0.2, 0.2)) for s in symbols}
    for i in range(n_bars):
        ts = start + timedelta(minutes=i)
        bar_row: Dict[str, dict] = {}
        for symbol in symbols:
            # Geometric walk with mild upward drift and mean-reverting noise
            shock = rng.normal(0.0004, 0.012)
            prices[symbol] = max(5.0, prices[symbol] * (1.0 + shock))
            close = float(round(prices[symbol], 2))
            open_p = float(round(close * (1.0 + rng.normal(0.0, 0.002)), 2))
            high = float(round(max(open_p, close) * (1.0 + abs(rng.normal(0.0, 0.003))), 2))
            low = float(round(min(open_p, close) * (1.0 - abs(rng.normal(0.0, 0.003))), 2))
            bar_row[symbol] = {
                "open": open_p, "high": high, "low": low, "close": close,
                "volume": float(rng.integers(50_000, 500_000)),
                "datetime": ts,
            }
        bars.append(bar_row)
    return bars


def replay_provider(bars: List[Dict[str, dict]]) -> BarProvider:
    """Turn a bar list into a provider: returns None after the last bar."""
    def provide(index: int) -> Optional[Dict[str, dict]]:
        if 0 <= index < len(bars):
            return bars[index]
        return None
    return provide


class TradingLoop:
    """Drives a TradingPipeline from a bar provider with heartbeat and shutdown.

    Args:
        pipeline: The connected TradingPipeline.
        bar_provider: callable(bar_index) → {symbol: bar} or None to stop.
        bar_interval: Seconds to sleep between bars (0 = replay speed).
        max_bars: Hard cap on iterations (None = until provider exhausts).
        exit_on_kill_switch: Stop the loop when the kill switch halts trading.
    """

    def __init__(
        self,
        pipeline: TradingPipeline,
        bar_provider: BarProvider,
        bar_interval: float = 0.0,
        max_bars: Optional[int] = None,
        exit_on_kill_switch: bool = True,
        metrics: Optional[RuntimeMetrics] = None,
    ) -> None:
        self.pipeline = pipeline
        self.bar_provider = bar_provider
        self.bar_interval = bar_interval
        self.max_bars = max_bars
        self.exit_on_kill_switch = exit_on_kill_switch
        self.metrics = metrics
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._heartbeat_count = 0

    def stop(self, *_args) -> None:
        """Request a graceful shutdown (safe to use as a signal handler)."""
        logger.info("Shutdown requested — stopping after current bar")
        self._stop_event.set()

    def pause(self) -> None:
        """Pause processing of subsequent bars without stopping the loop."""
        logger.info("Pause requested — pausing trading loop")
        self._pause_event.set()

    def resume(self) -> None:
        """Resume processing bars after a pause."""
        logger.info("Resume requested — resuming trading loop")
        self._pause_event.clear()

    @property
    def is_paused(self) -> bool:
        """Check if trading loop is currently paused."""
        return self._pause_event.is_set()

    def run(self) -> dict:
        """Run the loop until the provider exhausts, stop is requested, or cap."""
        index = 0
        last_summary: dict = {}
        while not self._stop_event.is_set():
            while self._pause_event.is_set() and not self._stop_event.is_set():
                time.sleep(0.05)
            if self._stop_event.is_set():
                break

            if self.max_bars is not None and index >= self.max_bars:
                logger.info("Reached max_bars=%s — stopping", self.max_bars)
                break
            try:
                bars = self.bar_provider(index)
                if bars is None:
                    logger.info("Bar provider exhausted after %d bars — stopping", index)
                    break
                ts = next(iter(bars.values())).get("datetime") if bars else None
                last_summary = self.pipeline.process_bar(bars, timestamp=ts)
                if self.metrics is not None:
                    self.metrics.record_snapshot(last_summary, self.pipeline.status())
                self._heartbeat(index, last_summary)
            except StaleDataError as exc:
                self.pipeline.kill_switch.activate(
                    KillSwitchReason.DATA_FEED_STALE,
                    detail=str(exc),
                )
                self.pipeline.audit_ledger.record(
                    action=AuditAction.KILL_SWITCH_TRIGGERED,
                    details={"reason": "DATA_FEED_STALE", "error": str(exc), "stage": "bar_provider"},
                )
                logger.critical("Stale data halted trading loop: %s", exc)
                if self.exit_on_kill_switch:
                    break
            except Exception as exc:
                logger.exception("Bar %d processing failed: %s", index, exc)
            index += 1
            if self.pipeline.kill_switch_triggered and self.exit_on_kill_switch:
                logger.critical("Kill switch active — halting trading loop")
                break
            if self.bar_interval > 0 and not self._stop_event.is_set():
                self._stop_event.wait(timeout=self.bar_interval)
        return {"bars_processed": index, "last": last_summary, "status": self.pipeline.status()}

    def _heartbeat(self, index: int, summary: dict) -> None:
        self._heartbeat_count += 1
        if index % 25 == 0 or index < 3:
            logger.info(
                "Heartbeat #%d bar=%d equity=%.2f positions=%s kill_switch=%s",
                self._heartbeat_count, index, summary.get("equity", 0.0),
                summary.get("positions"), summary.get("kill_switch_active"),
            )

    def install_signal_handlers(self) -> None:
        """Bind SIGINT/SIGTERM to graceful shutdown (no-op where unsupported)."""
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(os_signal, sig_name, None)
            if sig is not None:
                try:
                    os_signal.signal(sig, self.stop)
                except (ValueError, OSError):  # non-main thread or unsupported
                    pass


def build_default_pipeline(
    symbols: List[str],
    mode: str = "paper",
    initial_balance: float = 100_000.0,
    audit_path: Optional[str] = None,
    strategy: Optional[BaseStrategy] = None,
    ensemble: Optional[EnsembleSignalEngine] = None,
    drift_detector: Optional[DriftDetector] = None,
) -> TradingPipeline:
    """Assemble the standard paper-mode pipeline from environment-style args.

    Signal source defaults to a plain EnsembleSignalEngine (unfitted models →
    NO_TRADE) unless a strategy or a fitted ensemble is supplied — explicit
    beats accidental trading.
    """
    ledger = AuditLedger(log_path=audit_path) if audit_path else AuditLedger()
    broker = PaperBroker(initial_balance=initial_balance)
    source: EnsembleSignalEngine | BaseStrategy = ensemble or strategy or EnsembleSignalEngine()
    return TradingPipeline(
        broker=broker,
        symbols=symbols,
        signal_source=source,
        audit_ledger=ledger,
        drift_detector=drift_detector,
        dry_run=(mode == "dry_run"),
    )


def alpaca_polling_provider(
    provider: AlpacaDataProvider,
    symbols: List[str],
    *,
    require_market_session: bool = True,
) -> BarProvider:
    """Build a TradingLoop provider backed by Alpaca latest minute bars."""
    def provide(_index: int) -> Optional[Dict[str, dict]]:
        return provider.poll_latest_bars(
            symbols,
            require_market_session=require_market_session,
        )
    return provide


def build_alpaca_pipeline(
    symbols: List[str],
    *,
    profile: str = "alpaca_paper",
    audit_path: Optional[str] = None,
    strategy: Optional[BaseStrategy] = None,
    ensemble: Optional[EnsembleSignalEngine] = None,
) -> TradingPipeline:
    """Assemble the Alpaca production-paper pipeline.

    ``alpaca_live_locked`` requires PYROBOT_ALLOW_LIVE_TRADING=true. This is a
    hard guard so live trading cannot be enabled by a typo in PYROBOT_PROFILE.
    """
    profile = profile.lower()
    if profile not in {"alpaca_paper", "alpaca_live_locked"}:
        raise ValueError(f"Unsupported Alpaca profile: {profile}")
    live = profile == "alpaca_live_locked"
    if live and os.environ.get("PYROBOT_ALLOW_LIVE_TRADING", "").lower() != "true":
        raise RuntimeError(
            "Live Alpaca trading is locked. Set PYROBOT_ALLOW_LIVE_TRADING=true "
            "only after the paper-trading acceptance gates are satisfied."
        )

    ledger = AuditLedger(log_path=audit_path) if audit_path else AuditLedger()
    broker = AlpacaBroker(paper=not live)
    broker.authenticate()
    source: EnsembleSignalEngine | BaseStrategy = ensemble or strategy or EnsembleSignalEngine()
    return TradingPipeline(
        broker=broker,
        symbols=symbols,
        signal_source=source,
        audit_ledger=ledger,
        dry_run=False,
        risk_manager=RiskManager(limits=RiskLimits.conservative()),
    )


def _signal_source_from_env(symbols: List[str]) -> EnsembleSignalEngine | BaseStrategy:
    """Pick the demo signal source from PYROBOT_SIGNAL_SOURCE.

    'ensemble' (default): unfitted models — NO_TRADE unless real champion
        models are registered; nothing trades by accident.
    'example': the SMA-crossover ExampleStrategy — actually trades so the
        loop demonstrates the full path (signals, fills, audit, exits).
    """
    choice = os.environ.get("PYROBOT_SIGNAL_SOURCE", "ensemble").lower()
    if choice == "example":
        from pyrobot.strategies.base import ExampleStrategy

        return ExampleStrategy(strategy_id="demo_sma_cross", symbols=symbols)
    return EnsembleSignalEngine()


def main() -> None:
    """Console entrypoint: paper replay demo driven by environment variables."""
    symbols = [s.strip().upper() for s in os.environ.get("PYROBOT_SYMBOLS", "MSFT,AAPL").split(",") if s.strip()]
    n_bars = int(os.environ.get("PYROBOT_BARS", "500"))
    seed = int(os.environ.get("PYROBOT_SEED", "7"))
    mode = os.environ.get("PYROBOT_MODE", "paper").lower()
    balance = float(os.environ.get("PYROBOT_BALANCE", "100000"))
    audit_path = os.environ.get("PYROBOT_AUDIT_PATH", "data/audit/ledger.jsonl")
    metrics_path = os.environ.get("PYROBOT_METRICS_PATH", "data/metrics/runtime_metrics.jsonl")
    interval = float(os.environ.get("PYROBOT_BAR_INTERVAL", "0"))
    profile = os.environ.get("PYROBOT_PROFILE", "replay").lower()
    source = _signal_source_from_env(symbols)

    Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
    metrics = RuntimeMetrics(output_path=metrics_path)
    if profile == "replay":
        pipeline = build_default_pipeline(
            symbols=symbols, mode=mode, initial_balance=balance,
            audit_path=audit_path, strategy=source if isinstance(source, BaseStrategy) else None,
            ensemble=source if isinstance(source, EnsembleSignalEngine) else None,
        )
        provider = replay_provider(generate_replay_data(symbols, n_bars, seed=seed))
    elif profile in {"alpaca_paper", "alpaca_live_locked"}:
        pipeline = build_alpaca_pipeline(
            symbols=symbols,
            profile=profile,
            audit_path=audit_path,
            strategy=source if isinstance(source, BaseStrategy) else None,
            ensemble=source if isinstance(source, EnsembleSignalEngine) else None,
        )
        provider = alpaca_polling_provider(AlpacaDataProvider(), symbols)
    else:
        raise ValueError("PYROBOT_PROFILE must be replay, alpaca_paper, or alpaca_live_locked")

    logger.info(
        "Starting runtime loop: profile=%s symbols=%s bars=%d mode=%s source=%s balance=%.0f audit=%s",
        profile, symbols, n_bars, mode, type(source).__name__, balance, audit_path,
    )
    loop = TradingLoop(
        pipeline=pipeline,
        bar_provider=provider,
        bar_interval=interval,
        max_bars=n_bars,
        metrics=metrics,
    )
    loop.install_signal_handlers()
    result = loop.run()
    logger.info("Loop finished: %s", result)


if __name__ == "__main__":
    main()
