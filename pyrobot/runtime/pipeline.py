"""End-to-end trading pipeline connecting every subsystem.

This is the P0 integration the consultant report demanded — one connected
path from market data to audited orders:

    Data → Features → (AI ensemble | Strategy) → Risk gates → Execution
        → Audit ledger → Risk book updates

Every stage is observable: signals, risk decisions, submissions, fills, and
drift checks are recorded on the tamper-evident AuditLedger.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

from pyrobot.ai.drift import DriftDetector
from pyrobot.ai.ensemble import EnsembleSignalEngine
from pyrobot.audit.ledger import AuditAction, AuditLedger
from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import KillSwitchError
from pyrobot.execution.engine import ExecutionEngine
from pyrobot.execution.order_manager import OrderManager
from pyrobot.execution.reconciliation import AccountReconciler
from pyrobot.features.engine import FeatureEngine
from pyrobot.logging_config import get_logger
from pyrobot.models.signal import Signal, SignalAction
from pyrobot.risk.kill_switch import KillSwitch, KillSwitchReason
from pyrobot.risk.limits import RiskLimits
from pyrobot.risk.manager import RiskManager
from pyrobot.stock_frame import StockFrame
from pyrobot.strategies.base import BaseStrategy

logger = get_logger("runtime_pipeline")

# Drift recommendation → position-size scaling factor applied via RiskManager.
_DRIFT_SCALE = {
    "NO_ACTION": 1.0,
    "MONITOR_CLOSELY": 0.75,
    "RETRAIN_MODEL_AND_REDUCE_EXPOSURE": 0.25,
}

_EXIT_ACTIONS = {SignalAction.SELL, SignalAction.BUY_TO_COVER}


def _as_stock_frame(frame: pd.DataFrame, symbol: str) -> "StockFrame":
    """Wrap a per-symbol history DataFrame in a (symbol, datetime) StockFrame.

    BaseStrategy implementations expect the platform StockFrame type (the
    Indicators client reads its symbol groups), so strategy mode converts
    the pipeline's internal frame into one without re-parsing rows.
    """
    from pyrobot.stock_frame import StockFrame

    df = frame.copy()
    df["symbol"] = symbol
    if "datetime" not in df.columns:
        df["datetime"] = df.index
    sf = StockFrame.__new__(StockFrame)
    sf._data = []
    sf._frame = df.set_index(["symbol", "datetime"])
    sf._symbol_groups = None
    sf._symbol_rolling_groups = None
    return sf


class TradingPipeline:
    """Wires data, signals, risk, execution, and audit into one callable path.

    Args:
        broker: Broker adapter (PaperBroker for simulation).
        symbols: Universe to trade.
        signal_source: Either an EnsembleSignalEngine (AI mode) or a
            BaseStrategy (rule mode) — the source of trading Signals.
        risk_manager / order_manager / execution_engine / audit_ledger /
        kill_switch: Platform components; sensible defaults are built when
            omitted so the pipeline is always fully gated.
        feature_engine: Feature extraction (AI mode + drift checks).
        drift_detector: PSI drift monitor wired to RiskManager.set_model_risk_scale.
        dry_run: Forwarded to ExecutionEngine (shadow mode — no broker orders).
        history_window: Max bars retained per symbol for feature computation.
        drift_interval: Run a drift check every N processed bars.
        reconciliation_interval: Run broker/account reconciliation every N bars.
    """

    def __init__(
        self,
        broker: BrokerInterface,
        symbols: List[str],
        signal_source: EnsembleSignalEngine | BaseStrategy,
        risk_manager: Optional[RiskManager] = None,
        order_manager: Optional[OrderManager] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        audit_ledger: Optional[AuditLedger] = None,
        kill_switch: Optional[KillSwitch] = None,
        feature_engine: Optional[FeatureEngine] = None,
        drift_detector: Optional[DriftDetector] = None,
        account_id: str = "",
        dry_run: bool = False,
        history_window: int = 300,
        drift_interval: int = 50,
        min_history_bars: int = 60,
        reconciliation_interval: int = 25,
    ) -> None:
        self.broker = broker
        self.symbols = list(symbols)
        self.signal_source = signal_source
        self.is_ai_mode = isinstance(signal_source, EnsembleSignalEngine)
        self.audit_ledger = audit_ledger or AuditLedger()
        self.kill_switch = kill_switch or KillSwitch()
        self.risk_manager = risk_manager or RiskManager(
            kill_switch=self.kill_switch, limits=RiskLimits()
        )
        self.order_manager = order_manager or OrderManager()
        self.execution_engine = execution_engine or ExecutionEngine(
            broker=broker,
            order_manager=self.order_manager,
            kill_switch=self.kill_switch,
            risk_manager=self.risk_manager,
            audit_ledger=self.audit_ledger,
            account_id=account_id,
            dry_run=dry_run,
        )
        self.feature_engine = feature_engine or FeatureEngine()
        self.drift_detector = drift_detector
        self.history_window = history_window
        self.drift_interval = drift_interval
        self.min_history_bars = min_history_bars
        self.reconciliation_interval = reconciliation_interval
        self.account_reconciler = AccountReconciler(
            broker=broker,
            order_manager=self.order_manager,
            audit_ledger=self.audit_ledger,
            kill_switch=self.kill_switch,
            account_id=account_id,
        )

        self._history: Dict[str, List[dict]] = {s: [] for s in self.symbols}
        self._baseline_features: Optional[pd.DataFrame] = None
        self._bars_processed = 0
        self._current_prices: Dict[str, float] = {}
        self._daily_key: Optional[str] = None
        self.kill_switch_triggered: bool = False
        self._last_bar_at: Optional[datetime] = None
        self._last_symbol_bar_at: Dict[str, datetime] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def process_bar(self, bars: Dict[str, dict], timestamp: Optional[datetime] = None) -> dict:
        """Process one bar per symbol through the full pipeline.

        Args:
            bars: symbol → bar dict with open/high/low/close/volume.
            timestamp: Bar timestamp (defaults to now UTC).

        Returns:
            Summary dict: equity, positions, signals, order outcomes.
        """
        ts = timestamp or datetime.now(timezone.utc)
        self._bars_processed += 1
        self._last_bar_at = ts
        for symbol in bars:
            self._last_symbol_bar_at[symbol] = ts

        self._record_market_data(bars, ts)
        self._append_history(bars)
        self._push_prices_to_broker(bars)

        prices = {s: float(b.get("close", 0.0)) for s, b in bars.items()}
        self._current_prices.update(prices)
        positions = self._broker_positions()
        equity = self._equity(positions)

        self._risk_daily_reset(equity, ts)
        self.risk_manager.update_equity(equity)
        self.execution_engine.set_risk_context(positions, self._current_prices, equity)

        if (
            self.drift_detector is not None
            and self._bars_processed % self.drift_interval == 0
        ):
            self._run_drift_check()
        if self.reconciliation_interval > 0 and self._bars_processed % self.reconciliation_interval == 0:
            self._run_account_reconciliation()

        signals = self._generate_signals(bars, prices, positions)
        outcomes = [self._execute_signal(sig, positions, prices, equity) for sig in signals]

        return {
            "timestamp": ts.isoformat(),
            "bar_index": self._bars_processed,
            "equity": equity,
            "positions": positions,
            "signals": [s.to_dict() for s in signals],
            "orders": outcomes,
            "kill_switch_active": self.kill_switch.is_active,
        }

    # ── Stage implementations ─────────────────────────────────────────────────

    def _record_market_data(self, bars: Dict[str, dict], ts: datetime) -> None:
        self.audit_ledger.record(
            action=AuditAction.MARKET_DATA_RECORDED,
            details={"timestamp": ts.isoformat(), "closes": {s: b.get("close") for s, b in bars.items()}},
        )

    def _append_history(self, bars: Dict[str, dict]) -> None:
        for symbol, bar in bars.items():
            if symbol not in self._history:
                self._history[symbol] = []
            self._history[symbol].append(dict(bar))
            if len(self._history[symbol]) > self.history_window:
                self._history[symbol] = self._history[symbol][-self.history_window:]

    def _push_prices_to_broker(self, bars: Dict[str, dict]) -> None:
        """Push quotes to brokers that need them (PaperBroker fill engine)."""
        update = getattr(self.broker, "update_prices", None)
        if update is None:
            return
        try:
            update({
                symbol: {
                    "open": float(bar.get("open", bar.get("close", 0.0))),
                    "high": float(bar.get("high", bar.get("close", 0.0))),
                    "low": float(bar.get("low", bar.get("close", 0.0))),
                    "close": float(bar.get("close", 0.0)),
                    "last_price": float(bar.get("close", 0.0)),
                }
                for symbol, bar in bars.items()
            })
        except Exception as exc:
            logger.warning("Broker price push failed: %s", exc)

    def _history_frame(self, symbol: str) -> Optional[pd.DataFrame]:
        rows = self._history.get(symbol, [])
        if len(rows) < self.min_history_bars:
            return None
        return pd.DataFrame(rows)

    def _generate_signals(
        self,
        bars: Dict[str, dict],
        prices: Dict[str, float],
        positions: Dict[str, float],
    ) -> List[Signal]:
        """Generate one Signal per symbol from the configured source."""
        if self.kill_switch_triggered:
            return []

        signals: List[Signal] = []
        for symbol in self.symbols:
            bar = bars.get(symbol)
            if bar is None or prices.get(symbol, 0.0) <= 0:
                continue
            try:
                if self.is_ai_mode:
                    sig = self._ai_signal(symbol, positions)
                else:
                    sig = self._strategy_signal(symbol, bar)
            except Exception as exc:
                logger.error("Signal generation failed for %s: %s", symbol, exc)
                continue

            if sig is None:
                continue
            if sig.is_actionable:
                self.audit_ledger.record(
                    action=AuditAction.SIGNAL_GENERATED,
                    symbol=symbol,
                    strategy_id=sig.strategy_id,
                    model_id=sig.model_id,
                    details={"action": sig.action.value, "probability": sig.probability,
                             "confidence": sig.confidence, "reason": sig.reason},
                )
            signals.append(sig)
        return signals

    def _ai_signal(self, symbol: str, positions: Dict[str, float]) -> Optional[Signal]:
        """AI mode: features + regime + model probability via EnsembleSignalEngine.

        NaN feature cells from long rolling windows are left in place — the
        models sanitize inputs internally and the regime detector only needs
        the OHLCV columns.
        """
        frame = self._history_frame(symbol)
        if frame is None:
            return None
        features = self.feature_engine.extract_features(frame)
        combined = pd.concat([frame, features], axis=1)
        assert isinstance(self.signal_source, EnsembleSignalEngine)
        return self.signal_source.generate_signal(
            symbol=symbol,
            features_df=combined,
            position_state=positions,
        )

    def _strategy_signal(self, symbol: str, bar: dict) -> Optional[Signal]:
        """Rule mode: drive a BaseStrategy through its on_bar interface."""
        frame = self._history_frame(symbol)
        if frame is None:
            return None
        assert isinstance(self.signal_source, BaseStrategy)
        stock_frame = _as_stock_frame(frame, symbol)
        return self.signal_source.on_bar(symbol=symbol, bar=bar, stock_frame=stock_frame)

    def _execute_signal(
        self,
        signal: Signal,
        positions: Dict[str, float],
        prices: Dict[str, float],
        equity: float,
    ) -> dict:
        """Size, risk-gate, and submit one actionable signal through execution."""
        symbol = signal.symbol
        price = prices.get(symbol, 0.0)
        if not signal.is_actionable or price <= 0:
            return {"symbol": symbol, "action": signal.action.value, "status": "SKIPPED"}

        try:
            if signal.action in _EXIT_ACTIONS:
                held = positions.get(symbol, 0.0)
                quantity = abs(held)
                if quantity <= 0:
                    return {"symbol": symbol, "action": signal.action.value, "status": "NO_POSITION"}
            else:
                # WO-7: Fixed-fraction sizing only — win_rate/avg_win/avg_loss are
                # Kelly parameters that the fixed-fraction path ignores.
                # Confidence floor of 0.05 prevents zero-size on valid signals
                # (a calibrated probability near 0.5 still has a small edge);
                # it never applies to NO_TRADE paths (exits are quantity-based).
                quantity = self.risk_manager.calculate_position_size(
                    account_equity=equity,
                    win_rate=0.0,
                    avg_win=0.0,
                    avg_loss=0.0,
                    price=price,
                    confidence=max(0.05, signal.confidence),
                    method="fixed_fraction",
                )
                # Cap by the per-position exposure limit so routine orders pass
                # the risk gate (the gate stays authoritative for anything else).
                limits = self.risk_manager.limits
                max_qty = int(equity * limits.max_position_size_pct / price)
                quantity = min(quantity, max_qty)
                if quantity <= 0:
                    return {"symbol": symbol, "action": signal.action.value, "status": "ZERO_SIZE"}

            order = self.order_manager.create_from_signal(signal=signal, quantity=float(quantity))
            response = self.execution_engine.submit(order)
            fill = self._settle_order(order, response)
            return {
                "symbol": symbol,
                "action": signal.action.value,
                "client_order_id": order.client_order_id,
                "broker_order_id": response.get("order_id"),
                "status": fill.get("status", response.get("status", "SUBMITTED")),
                "fill_price": fill.get("avg_fill_price"),
                "fill_qty": fill.get("filled_quantity"),
            }
        except KillSwitchError as exc:
            self.kill_switch_triggered = True
            logger.critical("Kill switch halted trading: %s", exc)
            return {"symbol": symbol, "action": signal.action.value, "status": "KILL_SWITCH", "reason": str(exc)}
        except Exception as exc:
            logger.error("Order execution failed for %s: %s", symbol, exc)
            return {"symbol": symbol, "action": signal.action.value, "status": "ERROR", "reason": str(exc)}

    def _settle_order(self, order, response: dict) -> dict:
        """Poll the submitted order; on fills, update the risk book and strategy."""
        broker_order_id = response.get("order_id")
        if not broker_order_id:
            return {}
        try:
            status = self.execution_engine.poll_status(order.client_order_id)
        except Exception as exc:
            logger.warning("Poll failed for %s: %s", order.client_order_id, exc)
            return {}
        filled_qty = float(status.get("filled_quantity", 0.0) or 0.0)
        avg_price = float(status.get("avg_fill_price", 0.0) or 0.0)
        if filled_qty > 0 and avg_price > 0:
            self.risk_manager.record_fill(order, avg_price, filled_qty)
            if isinstance(self.signal_source, BaseStrategy):
                self.signal_source.on_order_fill({
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "quantity": filled_qty,
                    "fill_price": avg_price,
                    "status": status.get("status"),
                })
        return status

    def _run_drift_check(self) -> None:
        """PSI drift check on the primary symbol's features → risk scaling.

        Columns that are entirely NaN (rolling windows longer than the
        history) are dropped before comparing so short histories still work.
        """
        if self.drift_detector is None:
            return
        frame = self._history_frame(self.symbols[0]) if self.symbols else None
        if frame is None:
            return
        current = self.feature_engine.extract_features(frame)
        current = current.dropna(axis=1, how="all").dropna()
        if current.empty:
            return
        if self._baseline_features is None:
            self._baseline_features = current.iloc[: max(1, len(current) // 2)]
            return
        baseline = self._baseline_features
        common_cols = [c for c in current.columns if c in baseline.columns]
        if not common_cols:
            return
        report = self.drift_detector.evaluate_drift(
            baseline[common_cols], current[common_cols]
        )
        scale = _DRIFT_SCALE.get(report.recommendation, 1.0)
        self.risk_manager.set_model_risk_scale(scale, reason=f"PSI={report.max_psi:.3f}")
        self.audit_ledger.record(
            action=AuditAction.MODEL_DRIFT_CHECK,
            details={
                "max_psi": report.max_psi,
                "drift_detected": report.is_drift_detected,
                "recommendation": report.recommendation,
                "risk_scale": scale,
            },
        )

    def _run_account_reconciliation(self) -> None:
        """Compare risk-book positions with broker positions and halt on mismatch."""
        tracked = self.risk_manager.get_tracked_positions()
        expected_positions = {
            symbol: float(data.get("qty", 0.0) or 0.0)
            for symbol, data in tracked.items()
        }
        try:
            self.account_reconciler.reconcile(expected_positions=expected_positions)
        except Exception as exc:
            logger.error("Account reconciliation failed: %s", exc)
            self.kill_switch.activate(
                reason=KillSwitchReason.SYSTEM_HEALTH_FAILURE,
                detail=f"reconciliation_error={exc}",
            )
            self.audit_ledger.record(
                action=AuditAction.KILL_SWITCH_TRIGGERED,
                details={"reason": "SYSTEM_HEALTH_FAILURE", "stage": "account_reconciliation", "error": str(exc)},
            )

    # ── Account helpers ───────────────────────────────────────────────────────

    def _broker_positions(self) -> Dict[str, float]:
        try:
            raw = self.broker.get_positions() or []
        except Exception as exc:
            logger.warning("get_positions failed: %s", exc)
            return {}
        return {p["symbol"]: float(p["quantity"]) for p in raw if p.get("quantity")}

    def _equity(self, positions: Dict[str, float]) -> float:
        try:
            info = self.broker.get_account_info()
        except Exception:
            info = {}
        cash = float(info.get("cash_balance", 0.0) or 0.0)
        long_mv = float(info.get("long_market_value", 0.0) or 0.0)
        short_mv = float(info.get("short_market_value", 0.0) or 0.0)
        equity = cash + long_mv - short_mv
        if equity > 0:
            return equity
        # Fallback: price what we track ourselves
        return cash + sum(
            qty * self._current_prices.get(sym, 0.0) for sym, qty in positions.items()
        )

    def _risk_daily_reset(self, equity: float, ts: datetime) -> None:
        day_key = ts.strftime("%Y-%m-%d")
        if self._daily_key != day_key:
            self._daily_key = day_key
            self.risk_manager.set_daily_start(equity, day_key)

    def status(self) -> dict:
        """Operational snapshot of the pipeline."""
        now = datetime.now(timezone.utc)
        freshness: Dict[str, dict] = {}
        for s in self.symbols:
            sym_ts = self._last_symbol_bar_at.get(s)
            if sym_ts:
                aware_ts = sym_ts if sym_ts.tzinfo is not None else sym_ts.replace(tzinfo=timezone.utc)
                age = max(0.0, (now - aware_ts).total_seconds())
                freshness[s] = {"last_bar_at": sym_ts.isoformat(), "age_seconds": round(age, 2)}
            else:
                freshness[s] = {"last_bar_at": None, "age_seconds": None}

        return {
            "bars_processed": self._bars_processed,
            "last_bar_at": self._last_bar_at.isoformat() if self._last_bar_at else None,
            "data_freshness": freshness,
            "kill_switch_active": self.kill_switch.is_active,
            "kill_switch_triggered": self.kill_switch_triggered,
            "model_risk_scale": self.risk_manager.model_risk_scale,
            "risk": self.risk_manager.status(),
            "open_orders": len(self.order_manager.active_orders()),
        }
