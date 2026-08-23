"""Tests for pyrobot.risk.circuit_breaker — cooldown and HALF_OPEN semantics."""

from datetime import datetime, timedelta, timezone

import pytest

from pyrobot.risk.circuit_breaker import CircuitBreaker, CircuitState
from pyrobot.risk.limits import RiskLimits

COOLDOWN = 60


@pytest.fixture
def cb() -> CircuitBreaker:
    return CircuitBreaker(
        limits=RiskLimits(circuit_breaker_loss_streak=2),
        cooldown_seconds=COOLDOWN,
    )


def force_half_open(breaker: CircuitBreaker) -> None:
    """Open the breaker via a loss streak, then expire its cooldown."""
    breaker.record_trade_result(-10.0)
    breaker.record_trade_result(-10.0)
    assert breaker.is_open
    breaker._opened_at = datetime.now(timezone.utc) - timedelta(seconds=COOLDOWN * 10)
    assert breaker.state == CircuitState.HALF_OPEN


# ── Cooldown parameter ───────────────────────────────────────────────────────


class TestCooldownParameter:
    def test_default_cooldown_is_300_seconds(self):
        assert CircuitBreaker()._cooldown_seconds == 300

    def test_cooldown_seconds_parameter_is_honored(self):
        assert CircuitBreaker(cooldown_seconds=45)._cooldown_seconds == 45

    def test_zero_cooldown_is_not_swapped_for_default(self):
        assert CircuitBreaker(cooldown_seconds=0)._cooldown_seconds == 0


# ── HALF_OPEN single test order ──────────────────────────────────────────────


class TestHalfOpenTestOrder:
    def test_first_order_allowed_at_half_scale(self, cb):
        force_half_open(cb)
        assert cb.position_scale == 0.5
        assert cb.claim_test_order() is True

    def test_second_order_blocked_while_test_in_flight(self, cb):
        force_half_open(cb)
        assert cb.claim_test_order() is True
        assert cb.claim_test_order() is False
        assert cb.is_open is True

    def test_losing_test_trade_reopens_breaker(self, cb):
        force_half_open(cb)
        assert cb.claim_test_order() is True
        cb.record_trade_result(-5.0)
        assert cb.state == CircuitState.OPEN
        assert cb.is_open is True

    def test_winning_test_trade_closes_breaker(self, cb):
        force_half_open(cb)
        assert cb.claim_test_order() is True
        cb.record_trade_result(5.0)
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.position_scale == 1.0

    def test_reopened_breaker_offers_new_test_slot(self, cb):
        force_half_open(cb)
        assert cb.claim_test_order() is True
        cb.record_trade_result(-5.0)  # Re-opens
        cb._opened_at = datetime.now(timezone.utc) - timedelta(seconds=COOLDOWN * 10)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.claim_test_order() is True  # Fresh slot after cooldown

    def test_claim_allowed_when_closed(self, cb):
        assert cb.is_closed is True
        assert cb.claim_test_order() is True

    def test_claim_rejected_when_open(self, cb):
        cb.record_trade_result(-10.0)
        cb.record_trade_result(-10.0)
        assert cb.is_open is True
        assert cb.claim_test_order() is False

    def test_loss_streak_still_opens_from_closed(self, cb):
        cb.record_trade_result(-10.0)
        assert cb.is_closed is True
        cb.record_trade_result(-10.0)
        assert cb.is_open is True
