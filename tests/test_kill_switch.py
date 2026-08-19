"""Tests for pyrobot.risk.kill_switch — KillSwitch."""

import pytest
import threading
import time

from pyrobot.exceptions import KillSwitchError
from pyrobot.risk.kill_switch import KillSwitch, KillSwitchReason


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ks() -> KillSwitch:
    return KillSwitch()


# ── Initial state ─────────────────────────────────────────────────────────────

class TestInitialState:
    def test_not_active_on_init(self, ks):
        assert ks.is_active is False

    def test_current_event_none_on_init(self, ks):
        assert ks.current_event is None

    def test_history_empty_on_init(self, ks):
        assert ks.activation_history == []

    def test_guard_does_not_raise_when_inactive(self, ks):
        ks.guard()  # must not raise


# ── Activation ────────────────────────────────────────────────────────────────

class TestActivation:
    def test_activates_correctly(self, ks):
        ks.activate(KillSwitchReason.DAILY_LOSS_LIMIT, detail="loss=$500")
        assert ks.is_active is True

    def test_current_event_set_on_activation(self, ks):
        ks.activate(KillSwitchReason.MAX_DRAWDOWN, detail="DD=25%")
        event = ks.current_event
        assert event is not None
        assert event.reason == KillSwitchReason.MAX_DRAWDOWN
        assert event.detail == "DD=25%"
        assert event.activated_at is not None

    def test_guard_raises_when_active(self, ks):
        ks.activate(KillSwitchReason.BROKER_DISCONNECTED)
        with pytest.raises(KillSwitchError):
            ks.guard()

    def test_kill_switch_error_message(self, ks):
        ks.activate(KillSwitchReason.DATA_FEED_STALE, detail="feed timeout")
        with pytest.raises(KillSwitchError) as exc_info:
            ks.guard()
        assert "DATA_FEED_STALE" in str(exc_info.value)
        assert "feed timeout" in str(exc_info.value)

    def test_history_grows_on_activation(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        assert len(ks.activation_history) == 1

    def test_multiple_activations_recorded_in_history(self, ks):
        ks.activate(KillSwitchReason.DAILY_LOSS_LIMIT, detail="first")
        ks.activate(KillSwitchReason.MAX_DRAWDOWN, detail="second")  # idempotent active
        history = ks.activation_history
        assert len(history) == 2
        assert history[0].detail == "first"
        assert history[1].detail == "second"

    def test_second_activation_does_not_override_current_event(self, ks):
        ks.activate(KillSwitchReason.DAILY_LOSS_LIMIT, detail="first")
        ks.activate(KillSwitchReason.MAX_DRAWDOWN, detail="second")
        # Original event is preserved
        assert ks.current_event.reason == KillSwitchReason.DAILY_LOSS_LIMIT
        assert ks.current_event.detail == "first"

    def test_all_reasons_accepted(self, ks):
        for reason in KillSwitchReason:
            fresh = KillSwitch()
            fresh.activate(reason)
            assert fresh.is_active


# ── Reset ─────────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_requires_confirmed_true(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        with pytest.raises(ValueError, match="confirmed=True"):
            ks.reset(confirmed=False)

    def test_reset_without_confirmed_kwarg_raises(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        with pytest.raises((ValueError, TypeError)):
            ks.reset()

    def test_reset_deactivates(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        ks.reset(confirmed=True)
        assert ks.is_active is False

    def test_guard_passes_after_reset(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        ks.reset(confirmed=True)
        ks.guard()  # must not raise

    def test_history_preserved_after_reset(self, ks):
        ks.activate(KillSwitchReason.OPERATOR, detail="manual stop")
        ks.reset(confirmed=True)
        history = ks.activation_history
        assert len(history) == 1
        assert history[0].detail == "manual stop"

    def test_current_event_cleared_after_reset(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        ks.reset(confirmed=True)
        assert ks.current_event is None

    def test_can_reactivate_after_reset(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        ks.reset(confirmed=True)
        ks.activate(KillSwitchReason.SYSTEM_HEALTH_FAILURE)
        assert ks.is_active is True
        assert len(ks.activation_history) == 2


# ── Thread safety ─────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_activations_are_safe(self, ks):
        """Multiple threads activating concurrently must not corrupt state."""
        errors = []

        def activate_fn(reason):
            try:
                ks.activate(reason)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=activate_fn, args=(KillSwitchReason.OPERATOR,))
            for _ in range(20)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert ks.is_active is True

    def test_guard_is_thread_safe(self, ks):
        """Threads calling guard() concurrently after activation all raise."""
        ks.activate(KillSwitchReason.OPERATOR)
        results = []

        def guard_fn():
            try:
                ks.guard()
                results.append("no_raise")
            except KillSwitchError:
                results.append("raised")

        threads = [threading.Thread(target=guard_fn) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == "raised" for r in results)


# ── Repr ──────────────────────────────────────────────────────────────────────

class TestRepr:
    def test_repr_inactive(self, ks):
        assert "INACTIVE" in repr(ks)

    def test_repr_active(self, ks):
        ks.activate(KillSwitchReason.OPERATOR)
        r = repr(ks)
        assert "ACTIVE" in r
        assert "OPERATOR" in r
