"""Execution Engine — the single gateway for all order submissions.

Every order in the platform MUST pass through the ExecutionEngine.
No broker adapter should be called directly from a strategy.

The submission pipeline::

    ExecutionEngine.submit(order)
        │
        ├─ [1] KillSwitch.guard()              ← halt if kill switch active
        ├─ [2] Duplicate detection             ← via OrderManager
        ├─ [3] Order validation                ← symbol, qty, type checks
        ├─ [4] Risk pre-check                  ← (hook for future RiskEngine)
        ├─ [5] Broker.place_order(order)       ← canonical Order object
        ├─ [6] OrderManager.mark_submitted()   ← record broker_order_id
        └─ [7] Return broker response dict

On any transient error the submission is retried (via retry policy).
On permanent errors (rejected, invalid, kill switch) the error propagates.

Usage::

    engine = ExecutionEngine(
        broker=alpaca_broker,
        order_manager=order_manager,
        kill_switch=kill_switch,
        account_id="ACC123",
    )

    order = order_manager.create_from_signal(signal, quantity=10)
    response = engine.submit(order)
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from pyrobot.brokers.base import BrokerInterface
from pyrobot.exceptions import (
    KillSwitchError,
    OrderRejectedError,
    DuplicateOrderError,
    ExecutionError,
    NON_RETRYABLE_EXCEPTIONS,
)
from pyrobot.execution.order_manager import OrderManager
from pyrobot.logging_config import get_logger
from pyrobot.models.order import Order, OrderState, OrderType
from pyrobot.risk.kill_switch import KillSwitch
from pyrobot.risk.manager import RiskManager
from pyrobot.utils.retry import retry, is_retryable_order_error

logger = get_logger("execution_engine")


class ExecutionEngine:
    """Single gateway for all order submissions.

    Args:
        broker: The active :class:`BrokerInterface` implementation.
        order_manager: Platform :class:`OrderManager` instance.
        kill_switch: Platform :class:`KillSwitch` instance.
        account_id: Broker account identifier.
        max_retries: Maximum retry attempts for transient broker errors.
        dry_run: If True, log orders but do NOT submit to the broker.
            Useful for shadow mode testing.
    """

    def __init__(
        self,
        broker: BrokerInterface,
        order_manager: OrderManager,
        kill_switch: KillSwitch,
        account_id: str = "",
        max_retries: int = 3,
        dry_run: bool = False,
        risk_manager: RiskManager | None = None,
    ) -> None:
        self._broker = broker
        self._order_manager = order_manager
        self._kill_switch = kill_switch
        self._account_id = account_id
        self._max_retries = max_retries
        self._dry_run = dry_run
        self._risk_manager = risk_manager

        self._submission_count: int = 0
        self._failure_count: int = 0
        self._consecutive_failures: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def set_risk_context(
        self,
        positions: Dict[str, float],
        prices: Dict[str, float],
        equity: float,
    ) -> None:
        """Set the current risk context for pre-trade checks.

        Args:
            positions: Current positions (symbol → quantity).
            prices: Current prices (symbol → price).
            equity: Total portfolio equity.
        """
        self._risk_positions = positions
        self._risk_prices = prices
        self._risk_equity = equity

    def submit(self, order: Order) -> Dict:
        """Submit an order through the full execution pipeline.

        Args:
            order: A :class:`Order` instance previously registered with
                :class:`OrderManager`.

        Returns:
            Broker response dict with at minimum::

                {
                    "order_id": str,       # broker-assigned ID
                    "status": str,         # broker status string
                    "request_body": dict,  # what was sent
                }

        Raises:
            KillSwitchError: If the kill switch is active.
            DuplicateOrderError: If the order was already submitted.
            OrderRejectedError: If the broker rejects the order (non-retryable).
            ExecutionError: For other execution failures.
        """
        # ── Step 1: Kill switch guard ─────────────────────────────────────
        self._kill_switch.guard()

        # ── Step 2: Validate order state ──────────────────────────────────
        if order.status != OrderState.NEW:
            raise ExecutionError(
                f"Cannot submit order {order.client_order_id!r}: "
                f"expected state NEW, got {order.status.value}. "
                "This may indicate a duplicate submission attempt."
            )

        # ── Step 3: Basic order validation ────────────────────────────────
        self._validate(order)

        # ── Step 4: Risk pre-check hook (placeholder for RiskEngine) ──────
        self._pre_trade_risk_check(order)

        # ── Step 5: Submit to broker (with retry) ─────────────────────────
        logger.info(
            "Submitting order: coid=%s symbol=%s side=%s qty=%s type=%s dry_run=%s",
            order.client_order_id,
            order.symbol,
            order.side.value,
            order.quantity,
            order.order_type.value,
            self._dry_run,
        )

        if self._dry_run:
            return self._dry_run_response(order)

        try:
            response = self._submit_with_retry(order)
        except NON_RETRYABLE_EXCEPTIONS as exc:
            self._failure_count += 1
            self._consecutive_failures += 1
            self._order_manager.mark_rejected(
                order.client_order_id,
                reason=str(exc),
            )
            logger.error(
                "Order permanently rejected: coid=%s error=%s",
                order.client_order_id,
                exc,
            )
            raise

        except Exception as exc:
            self._failure_count += 1
            self._consecutive_failures += 1
            # Transient errors that exhausted all retries → UNKNOWN
            self._order_manager.mark_unknown(
                order.client_order_id,
                reason=f"Exhausted retries: {exc}",
            )
            logger.error(
                "Order state set to UNKNOWN after retry exhaustion: coid=%s error=%s",
                order.client_order_id,
                exc,
            )
            raise ExecutionError(
                f"Order submission failed after {self._max_retries} retries: {exc}"
            ) from exc

        # ── Step 6: Record broker_order_id ────────────────────────────────
        broker_order_id = response.get("order_id", "")
        if not broker_order_id:
            logger.warning(
                "Broker response missing order_id for coid=%s. "
                "Order will remain in SUBMITTED state.",
                order.client_order_id,
            )

        self._order_manager.mark_submitted(
            order.client_order_id,
            broker_order_id=broker_order_id,
        )

        self._submission_count += 1
        self._consecutive_failures = 0  # Reset on success

        logger.info(
            "Order submitted successfully: coid=%s broker_id=%s status=%s",
            order.client_order_id,
            broker_order_id,
            response.get("status"),
        )

        return response

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _validate(self, order: Order) -> None:
        """Basic order field validation before broker submission.

        Raises:
            ValueError: On invalid order fields.
        """
        if not order.symbol or not order.symbol.strip():
            raise ValueError(
                f"Order {order.client_order_id!r} has an empty symbol."
            )

        if order.quantity <= 0:
            raise ValueError(
                f"Order {order.client_order_id!r} has invalid quantity "
                f"{order.quantity} — must be positive."
            )

        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            if order.limit_price is None or order.limit_price <= 0:
                raise ValueError(
                    f"Order {order.client_order_id!r} is type {order.order_type.value} "
                    "but has no valid limit_price."
                )

        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if order.stop_price is None or order.stop_price <= 0:
                raise ValueError(
                    f"Order {order.client_order_id!r} is type {order.order_type.value} "
                    "but has no valid stop_price."
                )

    def _pre_trade_risk_check(self, order: Order) -> None:
        """Run pre-trade risk validation via the RiskManager.

        If no RiskManager is configured, this is a no-op (backward compatible).
        If RiskManager rejects the order, raises the appropriate RiskError.

        Raises:
            RiskError: If the risk manager rejects the order.
            KillSwitchError: If drawdown or daily loss limits are breached.
        """
        if self._risk_manager is None:
            return

        # RiskManager.check_order will raise KillSwitchError on
        # drawdown/daily loss breach, or return (False, reason) for soft rejections
        approved, reason = self._risk_manager.check_order(
            order=order,
            positions=getattr(self, "_risk_positions", {}),
            prices=getattr(self, "_risk_prices", {}),
            equity=getattr(self, "_risk_equity", 0.0),
        )
        if not approved:
            raise ExecutionError(
                f"Risk manager rejected order {order.client_order_id!r}: {reason}"
            )

    def _submit_with_retry(self, order: Order) -> Dict:
        """Submit the order to the broker, retrying on transient errors.

        Uses the :func:`retry` decorator pattern inline for configurable
        max_retries.
        """
        order_dict = order.to_legacy_dict()
        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                return self._broker.place_order(
                    account=self._account_id,
                    order=order_dict,
                )
            except Exception as exc:
                last_exc = exc

                # Non-retryable → propagate immediately
                if isinstance(exc, NON_RETRYABLE_EXCEPTIONS):
                    raise

                if not is_retryable_order_error(exc):
                    raise

                if attempt >= self._max_retries:
                    break

                import time
                delay = min(1.0 * (2 ** attempt), 30.0)
                logger.warning(
                    "Transient broker error (attempt %d/%d) for coid=%s: %s — "
                    "retrying in %.1fs",
                    attempt + 1,
                    self._max_retries + 1,
                    order.client_order_id,
                    exc,
                    delay,
                )
                time.sleep(delay)

        raise last_exc  # type: ignore[misc]

    def _dry_run_response(self, order: Order) -> Dict:
        """Return a synthetic broker response for dry-run / shadow mode."""
        logger.info(
            "[DRY RUN] Order NOT submitted to broker: coid=%s symbol=%s side=%s qty=%s",
            order.client_order_id,
            order.symbol,
            order.side.value,
            order.quantity,
        )
        fake_broker_id = f"DRY_{order.client_order_id[:8]}"
        self._order_manager.mark_submitted(order.client_order_id, fake_broker_id)
        return {
            "order_id": fake_broker_id,
            "status": "DRY_RUN",
            "request_body": order.to_legacy_dict(),
        }

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @property
    def stats(self) -> Dict:
        """Return basic submission statistics."""
        result = {
            "submission_count": self._submission_count,
            "failure_count": self._failure_count,
            "consecutive_failures": self._consecutive_failures,
            "kill_switch_active": self._kill_switch.is_active,
            "dry_run": self._dry_run,
        }
        if self._risk_manager is not None:
            result["risk_manager"] = self._risk_manager.status()
        return result
