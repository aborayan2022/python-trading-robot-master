"""Runtime supervisor for PyRobot console.

Manages the background TradingLoop thread, lifecycle states (STOPPED, STARTING,
RUNNING, PAUSED, STOPPING, ERROR), and dynamic runtime configuration.
"""

from __future__ import annotations

import dataclasses
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.logging_config import get_logger
from pyrobot.monitoring import RuntimeMetrics
from pyrobot.risk.limits import RiskLimits
from pyrobot.runtime.loop import (
    TradingLoop,
    alpaca_polling_provider,
    build_alpaca_pipeline,
    build_default_pipeline,
    generate_replay_data,
    replay_provider,
)
from pyrobot.runtime.pipeline import TradingPipeline
from pyrobot.strategies.base import BaseStrategy, ExampleStrategy

logger = get_logger("console_supervisor")


class SupervisorState(str, Enum):
    """Lifecycle states of the trading loop supervisor."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


@dataclass
class ConsoleConfig:
    """Unified runtime configuration for the management console."""

    profile: str = "replay"  # "replay" | "alpaca_paper" | "alpaca_live_locked"
    symbols: List[str] = field(default_factory=lambda: ["MSFT", "AAPL"])
    signal_source: str = "example"  # "example" | "ensemble"
    bar_interval: float = 1.0
    n_bars: int = 500
    seed: int = 7
    initial_balance: float = 100_000.0
    mode: str = "paper"  # "paper" | "dry_run"
    audit_path: str = "data/audit/ledger.jsonl"
    metrics_path: str = "data/metrics/runtime_metrics.jsonl"
    dry_run: bool = False
    allow_live_trading: bool = False

    @classmethod
    def from_env(cls) -> ConsoleConfig:
        """Construct console config from system environment variables."""
        symbols_str = os.environ.get("PYROBOT_SYMBOLS", "MSFT,AAPL")
        symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
        return cls(
            profile=os.environ.get("PYROBOT_PROFILE", "replay").lower(),
            symbols=symbols,
            signal_source=os.environ.get("PYROBOT_SIGNAL_SOURCE", "example").lower(),
            bar_interval=float(os.environ.get("PYROBOT_BAR_INTERVAL", "1.0")),
            n_bars=int(os.environ.get("PYROBOT_BARS", "500")),
            seed=int(os.environ.get("PYROBOT_SEED", "7")),
            initial_balance=float(os.environ.get("PYROBOT_BALANCE", "100000")),
            mode=os.environ.get("PYROBOT_MODE", "paper").lower(),
            audit_path=os.environ.get("PYROBOT_AUDIT_PATH", "data/audit/ledger.jsonl"),
            metrics_path=os.environ.get("PYROBOT_METRICS_PATH", "data/metrics/runtime_metrics.jsonl"),
            dry_run=(os.environ.get("PYROBOT_MODE", "").lower() == "dry_run"),
            allow_live_trading=(os.environ.get("PYROBOT_ALLOW_LIVE_TRADING", "").lower() == "true"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConsoleConfig:
        """Create config from dictionary with validation."""
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        if "symbols" in filtered and isinstance(filtered["symbols"], list):
            filtered["symbols"] = [str(s).strip().upper() for s in filtered["symbols"] if str(s).strip()]
        return cls(**filtered)


class RuntimeSupervisor:
    """Oversees the single-process background trading loop and exposes telemetry."""

    def __init__(self, config: Optional[ConsoleConfig] = None) -> None:
        self._lock = threading.RLock()
        self.config: ConsoleConfig = config or ConsoleConfig.from_env()
        self._state: SupervisorState = SupervisorState.STOPPED
        self._pipeline: Optional[TradingPipeline] = None
        self._loop: Optional[TradingLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._metrics: Optional[RuntimeMetrics] = None
        self._audit_ledger: Optional[AuditLedger] = None
        self._last_error: Optional[str] = None
        self._last_bar_at: Optional[datetime] = None
        self._started_at: Optional[datetime] = None
        self._bars_processed: int = 0

    @property
    def state(self) -> SupervisorState:
        with self._lock:
            return self._state

    @property
    def pipeline(self) -> Optional[TradingPipeline]:
        with self._lock:
            return self._pipeline

    @property
    def loop(self) -> Optional[TradingLoop]:
        with self._lock:
            return self._loop

    @property
    def audit_ledger(self) -> AuditLedger:
        with self._lock:
            if self._pipeline and self._pipeline.audit_ledger:
                return self._pipeline.audit_ledger
            if self._audit_ledger is None:
                Path(self.config.audit_path).parent.mkdir(parents=True, exist_ok=True)
                self._audit_ledger = AuditLedger(log_path=self.config.audit_path)
            return self._audit_ledger

    @property
    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    # ── Lifecycle Control ─────────────────────────────────────────────────────

    def start(self, config: Optional[ConsoleConfig] = None) -> bool:
        """Start the trading loop thread with the provided or current config."""
        with self._lock:
            if self._state in (SupervisorState.RUNNING, SupervisorState.STARTING, SupervisorState.PAUSED):
                logger.warning("Cannot start: supervisor is in state %s", self._state.value)
                return False

            if config is not None:
                self.config = config

            self._state = SupervisorState.STARTING
            self._last_error = None
            self._started_at = datetime.now(timezone.utc)

            try:
                # Ensure directories exist
                Path(self.config.audit_path).parent.mkdir(parents=True, exist_ok=True)
                Path(self.config.metrics_path).parent.mkdir(parents=True, exist_ok=True)

                self._metrics = RuntimeMetrics(output_path=self.config.metrics_path)

                # Select signal source
                if self.config.signal_source == "example":
                    source: Any = ExampleStrategy(strategy_id="demo_sma_cross", symbols=self.config.symbols)
                else:
                    from pyrobot.ai.ensemble import EnsembleSignalEngine

                    source = EnsembleSignalEngine()

                # Build Pipeline and Provider
                if self.config.profile == "replay":
                    self._pipeline = build_default_pipeline(
                        symbols=self.config.symbols,
                        mode=self.config.mode,
                        initial_balance=self.config.initial_balance,
                        audit_path=self.config.audit_path,
                        strategy=source if isinstance(source, BaseStrategy) else None,
                    )
                    bars_data = generate_replay_data(
                        self.config.symbols,
                        n_bars=self.config.n_bars,
                        seed=self.config.seed,
                    )
                    provider = replay_provider(bars_data)
                elif self.config.profile in {"alpaca_paper", "alpaca_live_locked"}:
                    from pyrobot.data.alpaca import AlpacaDataProvider

                    self._pipeline = build_alpaca_pipeline(
                        symbols=self.config.symbols,
                        profile=self.config.profile,
                        audit_path=self.config.audit_path,
                        strategy=source if isinstance(source, BaseStrategy) else None,
                    )
                    provider = alpaca_polling_provider(AlpacaDataProvider(), self.config.symbols)
                else:
                    raise ValueError(f"Unknown profile: {self.config.profile}")

                self._loop = TradingLoop(
                    pipeline=self._pipeline,
                    bar_provider=provider,
                    bar_interval=self.config.bar_interval,
                    max_bars=self.config.n_bars if self.config.profile == "replay" else None,
                    metrics=self._metrics,
                )

                # Launch thread
                self._thread = threading.Thread(
                    target=self._run_loop_wrapper,
                    name="TradingLoopThread",
                    daemon=True,
                )
                self._thread.start()
                self._state = SupervisorState.RUNNING

                self.audit_ledger.record(
                    action=AuditAction.CONTROL_ACTION,
                    details={
                        "action": "START",
                        "profile": self.config.profile,
                        "symbols": self.config.symbols,
                        "signal_source": self.config.signal_source,
                    },
                )
                logger.info("Supervisor started trading loop in background thread.")
                return True

            except Exception as exc:
                self._state = SupervisorState.ERROR
                self._last_error = str(exc)
                logger.exception("Failed to start supervisor: %s", exc)
                return False

    def _run_loop_wrapper(self) -> None:
        """Internal worker function executed in the background thread."""
        try:
            if self._loop is not None:
                result = self._loop.run()
                self._bars_processed = result.get("bars_processed", 0)
                logger.info("Trading loop finished naturally: %s", result)
        except Exception as exc:
            with self._lock:
                self._state = SupervisorState.ERROR
                self._last_error = str(exc)
            logger.exception("Trading loop raised exception: %s", exc)
        finally:
            with self._lock:
                if self._state not in (SupervisorState.ERROR, SupervisorState.STOPPED):
                    self._state = SupervisorState.STOPPED

    def stop(self, timeout: float = 5.0) -> bool:
        """Request graceful stop of the trading loop."""
        with self._lock:
            if self._state in (SupervisorState.STOPPED, SupervisorState.STOPPING):
                return True

            self._state = SupervisorState.STOPPING
            if self._loop is not None:
                self._loop.stop()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        with self._lock:
            self._state = SupervisorState.STOPPED
            self.audit_ledger.record(
                action=AuditAction.CONTROL_ACTION,
                details={"action": "STOP"},
            )
            logger.info("Supervisor stopped trading loop.")
            return True

    def pause(self) -> bool:
        """Pause the running trading loop between bars."""
        with self._lock:
            if self._state != SupervisorState.RUNNING or self._loop is None:
                logger.warning("Cannot pause: loop is not RUNNING")
                return False
            self._loop.pause()
            self._state = SupervisorState.PAUSED
            self.audit_ledger.record(
                action=AuditAction.CONTROL_ACTION,
                details={"action": "PAUSE"},
            )
            logger.info("Supervisor paused trading loop.")
            return True

    def resume(self) -> bool:
        """Resume the paused trading loop."""
        with self._lock:
            if self._state != SupervisorState.PAUSED or self._loop is None:
                logger.warning("Cannot resume: loop is not PAUSED")
                return False
            self._loop.resume()
            self._state = SupervisorState.RUNNING
            self.audit_ledger.record(
                action=AuditAction.CONTROL_ACTION,
                details={"action": "RESUME"},
            )
            logger.info("Supervisor resumed trading loop.")
            return True

    def apply_config(self, new_config: ConsoleConfig) -> bool:
        """Gracefully stop current loop and restart with new configuration."""
        logger.info("Applying new configuration: %s", new_config.to_dict())
        self.stop(timeout=5.0)
        with self._lock:
            self.config = new_config
            success = self.start(new_config)
            self.audit_ledger.record(
                action=AuditAction.CONTROL_ACTION,
                details={"action": "APPLY_CONFIG", "config": new_config.to_dict(), "success": success},
            )
            return success

    # ── Telemetry & Queries ───────────────────────────────────────────────────

    def get_overview(self) -> Dict[str, Any]:
        """Aggregate full operational snapshot for the overview dashboard."""
        with self._lock:
            pipeline_status: Dict[str, Any] = {}
            if self._pipeline:
                try:
                    pipeline_status = self._pipeline.status()
                except Exception as exc:
                    pipeline_status = {"error": str(exc)}

            # Extract broker equity & positions
            equity = 0.0
            positions: Dict[str, float] = {}
            if self._pipeline and self._pipeline.broker:
                try:
                    info = self._pipeline.broker.get_account_info() or {}
                    cash = float(info.get("cash_balance", 0.0) or 0.0)
                    long_mv = float(info.get("long_market_value", 0.0) or 0.0)
                    short_mv = float(info.get("short_market_value", 0.0) or 0.0)
                    equity = cash + long_mv - short_mv
                    raw_pos = self._pipeline.broker.get_positions() or []
                    positions = {p["symbol"]: float(p["quantity"]) for p in raw_pos if p.get("quantity")}
                except Exception:
                    equity = self.config.initial_balance

            # Risk details
            risk_info: Dict[str, Any] = pipeline_status.get("risk", {})
            drawdown = float(risk_info.get("drawdown", 0.0) or 0.0)
            daily_loss_pct = float(risk_info.get("daily_loss_pct", 0.0) or 0.0)
            daily_pnl = float(risk_info.get("daily_realized_pnl", 0.0) or 0.0)
            circuit_breaker_state = risk_info.get("circuit_breaker_state", "CLOSED")
            circuit_breaker_scale = float(risk_info.get("position_scale", 1.0) or 1.0)
            model_risk_scale = float(pipeline_status.get("model_risk_scale", 1.0) or 1.0)

            # Market session check
            from pyrobot.utils import is_market_open

            market_open = is_market_open()

            # Alpaca broker status check
            alpaca_status = {
                "connected": self.config.profile in {"alpaca_paper", "alpaca_live_locked"},
                "mode": self.config.profile,
                "allow_live": self.config.allow_live_trading or (os.environ.get("PYROBOT_ALLOW_LIVE_TRADING", "").lower() == "true"),
            }

            return {
                "state": self._state.value,
                "profile": self.config.profile,
                "symbols": self.config.symbols,
                "signal_source": self.config.signal_source,
                "equity": round(equity, 2),
                "drawdown": round(drawdown, 4),
                "daily_pnl": round(daily_pnl, 2),
                "daily_loss_pct": round(daily_loss_pct, 4),
                "kill_switch_active": pipeline_status.get("kill_switch_active", False),
                "kill_switch_triggered": pipeline_status.get("kill_switch_triggered", False),
                "circuit_breaker": {
                    "state": circuit_breaker_state,
                    "scale": circuit_breaker_scale,
                },
                "model_risk_scale": model_risk_scale,
                "data_freshness": pipeline_status.get("data_freshness", {}),
                "last_bar_at": pipeline_status.get("last_bar_at"),
                "bars_processed": pipeline_status.get("bars_processed", self._bars_processed),
                "open_orders_count": pipeline_status.get("open_orders", 0),
                "positions_count": len(positions),
                "market_session": {
                    "is_open": market_open,
                    "session": "REGULAR" if market_open else "CLOSED",
                },
                "alpaca_status": alpaca_status,
                "last_error": self._last_error,
                "started_at": self._started_at.isoformat() if self._started_at else None,
            }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Retrieve detailed position list with current valuation."""
        with self._lock:
            if not self._pipeline or not self._pipeline.broker:
                return []
            try:
                raw_positions = self._pipeline.broker.get_positions() or []
                prices = getattr(self._pipeline, "_current_prices", {})
                result = []
                for p in raw_positions:
                    sym = p.get("symbol", "")
                    qty = float(p.get("quantity", 0.0))
                    avg_price = float(p.get("cost_basis", p.get("entry_price", 0.0)) or 0.0)
                    cur_price = prices.get(sym, avg_price)
                    market_val = qty * cur_price
                    unrealized_pnl = (cur_price - avg_price) * qty if avg_price > 0 else 0.0
                    result.append({
                        "symbol": sym,
                        "quantity": qty,
                        "entry_price": avg_price,
                        "current_price": cur_price,
                        "market_value": round(market_val, 2),
                        "unrealized_pnl": round(unrealized_pnl, 2),
                        "unrealized_pnl_pct": round((unrealized_pnl / (avg_price * qty)) * 100, 2) if (avg_price * qty) > 0 else 0.0,
                    })
                return result
            except Exception as exc:
                logger.warning("Failed to get positions: %s", exc)
                return []

    def get_orders(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve orders from the active OrderManager."""
        with self._lock:
            if not self._pipeline or not self._pipeline.order_manager:
                return []
            try:
                orders = self._pipeline.order_manager.all_orders()
                if state:
                    state_upper = state.upper()
                    orders = [o for o in orders if getattr(o.state, "value", str(o.state)) == state_upper]
                # Return most recent orders first
                return [o.to_dict() for o in reversed(orders[-100:])]
            except Exception as exc:
                logger.warning("Failed to get orders: %s", exc)
                return []

    def get_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve latest generated signals from the audit ledger."""
        with self._lock:
            try:
                events = self.audit_ledger.get_events(action=AuditAction.SIGNAL_GENERATED, limit=limit)
                return [e.to_dict() for e in events]
            except Exception as exc:
                logger.warning("Failed to get signals: %s", exc)
                return []

    def get_audit_events(
        self,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieve audit ledger events with optional action filter."""
        with self._lock:
            try:
                audit_action = AuditAction(action) if action else None
                events = self.audit_ledger.get_events(action=audit_action)
                sliced = events[offset : offset + limit] if offset > 0 else events[-limit:]
                return [e.to_dict() for e in sliced]
            except Exception as exc:
                logger.warning("Failed to get audit events: %s", exc)
                return []

    def get_risk_limits(self) -> Dict[str, Any]:
        """Retrieve current RiskLimits from RiskManager."""
        with self._lock:
            if self._pipeline and self._pipeline.risk_manager:
                return dataclasses.asdict(self._pipeline.risk_manager.limits)
            return dataclasses.asdict(RiskLimits())

    def update_risk_limits(self, new_limits_dict: Dict[str, Any]) -> bool:
        """Update risk limits under validation and lock, recording audit event."""
        with self._lock:
            current_dict = self.get_risk_limits()
            current_dict.update(new_limits_dict)
            new_limits = RiskLimits(**current_dict)
            new_limits.validate()

            if self._pipeline and self._pipeline.risk_manager:
                self._pipeline.risk_manager.update_limits(new_limits)

            self.audit_ledger.record(
                action=AuditAction.CONTROL_ACTION,
                details={
                    "action": "UPDATE_RISK_LIMITS",
                    "limits": dataclasses.asdict(new_limits),
                },
            )
            return True
