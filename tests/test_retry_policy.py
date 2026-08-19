"""Tests for pyrobot.utils.retry — retry policy and exception classification."""

import pytest
import time
from unittest.mock import MagicMock, patch, call

from pyrobot.utils.retry import (
    is_retryable_exception,
    is_retryable_order_error,
    retry,
)
from pyrobot.exceptions import (
    BrokerRateLimitError,
    BrokerTimeoutError,
    BrokerConnectionError,
    OrderRejectedError,
    InvalidSymbolError,
    AuthenticationError,
    KillSwitchError,
    DuplicateOrderError,
)


# ── is_retryable_exception ────────────────────────────────────────────────────

class TestIsRetryableException:

    def test_rate_limit_error_is_retryable(self):
        assert is_retryable_exception(BrokerRateLimitError("429")) is True

    def test_timeout_error_is_retryable(self):
        assert is_retryable_exception(BrokerTimeoutError("timeout")) is True

    def test_connection_error_is_retryable(self):
        assert is_retryable_exception(BrokerConnectionError("disconnected")) is True

    def test_standard_connection_error_is_retryable(self):
        assert is_retryable_exception(ConnectionError("reset")) is True

    def test_standard_timeout_is_retryable(self):
        assert is_retryable_exception(TimeoutError("timed out")) is True

    def test_order_rejected_is_not_retryable(self):
        assert is_retryable_exception(OrderRejectedError("rejected")) is False

    def test_invalid_symbol_is_not_retryable(self):
        assert is_retryable_exception(InvalidSymbolError("bad symbol")) is False

    def test_auth_error_is_not_retryable(self):
        assert is_retryable_exception(AuthenticationError("auth failed")) is False

    def test_kill_switch_is_not_retryable(self):
        assert is_retryable_exception(KillSwitchError()) is False

    def test_duplicate_order_is_not_retryable(self):
        assert is_retryable_exception(DuplicateOrderError("duplicate")) is False

    def test_generic_exception_with_timeout_keyword_is_retryable(self):
        exc = Exception("connection timed out")
        assert is_retryable_exception(exc) is True

    def test_generic_exception_with_rejected_keyword_is_not_retryable(self):
        exc = Exception("order rejected by broker")
        assert is_retryable_exception(exc) is False


# ── is_retryable_order_error ──────────────────────────────────────────────────

class TestIsRetryableOrderError:

    def test_transient_error_retryable(self):
        assert is_retryable_order_error(BrokerTimeoutError("timeout")) is True

    def test_rejected_not_retryable(self):
        assert is_retryable_order_error(OrderRejectedError("insufficient funds")) is False

    def test_invalid_not_retryable(self):
        assert is_retryable_order_error(InvalidSymbolError("BADTICKER")) is False

    def test_kill_switch_not_retryable(self):
        assert is_retryable_order_error(KillSwitchError()) is False


# ── @retry decorator ──────────────────────────────────────────────────────────

class TestRetryDecorator:

    def test_succeeds_on_first_try(self):
        mock_fn = MagicMock(return_value="ok")

        @retry(max_attempts=3, base_delay=0.01)
        def fn():
            return mock_fn()

        result = fn()
        assert result == "ok"
        assert mock_fn.call_count == 1

    def test_retries_on_transient_error(self):
        call_count = {"n": 0}

        @retry(max_attempts=2, base_delay=0.01, jitter=False)
        def fn():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise BrokerTimeoutError("timeout")
            return "success"

        result = fn()
        assert result == "success"
        assert call_count["n"] == 3

    def test_raises_after_max_attempts(self):
        call_count = {"n": 0}

        @retry(max_attempts=2, base_delay=0.01, jitter=False)
        def fn():
            call_count["n"] += 1
            raise BrokerTimeoutError("always fails")

        with pytest.raises(BrokerTimeoutError):
            fn()

        assert call_count["n"] == 3  # 1 original + 2 retries

    def test_does_not_retry_non_retryable_error(self):
        call_count = {"n": 0}

        @retry(max_attempts=3, base_delay=0.01)
        def fn():
            call_count["n"] += 1
            raise OrderRejectedError("rejected")

        with pytest.raises(OrderRejectedError):
            fn()

        assert call_count["n"] == 1  # No retries

    def test_does_not_retry_kill_switch(self):
        call_count = {"n": 0}

        @retry(max_attempts=3, base_delay=0.01)
        def fn():
            call_count["n"] += 1
            raise KillSwitchError()

        with pytest.raises(KillSwitchError):
            fn()

        assert call_count["n"] == 1

    def test_custom_retryable_check(self):
        """Custom check that retries ValueError."""
        call_count = {"n": 0}

        @retry(
            max_attempts=2,
            base_delay=0.01,
            jitter=False,
            retryable_check=lambda exc: isinstance(exc, ValueError),
        )
        def fn():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ValueError("custom")
            return "done"

        result = fn()
        assert result == "done"
        assert call_count["n"] == 3

    def test_preserves_function_name(self):
        @retry(max_attempts=1, base_delay=0.01)
        def my_special_function():
            pass

        assert my_special_function.__name__ == "my_special_function"

    def test_preserves_return_value(self):
        @retry(max_attempts=2, base_delay=0.01)
        def fn():
            return {"data": [1, 2, 3]}

        assert fn() == {"data": [1, 2, 3]}

    def test_passes_args_and_kwargs(self):
        received = {}

        @retry(max_attempts=1, base_delay=0.01)
        def fn(a, b, c=None):
            received.update({"a": a, "b": b, "c": c})
            return True

        fn(1, 2, c="hello")
        assert received == {"a": 1, "b": 2, "c": "hello"}
