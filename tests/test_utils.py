"""Tests for utility modules."""

from datetime import datetime, timedelta, timezone

import pytest

from pyrobot.utils.retry import is_retryable_exception, is_retryable_order_error, retry
from pyrobot.utils.timezone import (
    is_market_open,
    parse_datetime,
    to_utc,
    utc_now,
)


class TestRetryableException:
    """Tests for is_retryable_exception."""

    def test_connection_error_is_retryable(self):
        assert is_retryable_exception(ConnectionError("timeout")) is True

    def test_timeout_error_is_retryable(self):
        assert is_retryable_exception(TimeoutError("request timed out")) is True

    def test_os_error_is_retryable(self):
        assert is_retryable_exception(OSError("connection refused")) is True

    def test_value_error_is_not_retryable(self):
        assert is_retryable_exception(ValueError("invalid input")) is False

    def test_type_error_is_not_retryable(self):
        assert is_retryable_exception(TypeError("wrong type")) is False

    def test_timeout_message_is_retryable(self):
        exc = Exception("Connection timed out")
        assert is_retryable_exception(exc) is True

    def test_connection_refused_is_retryable(self):
        exc = Exception("Connection refused")
        assert is_retryable_exception(exc) is True


class TestRetryableOrderError:
    """Tests for is_retryable_order_error."""

    def test_rejected_is_not_retryable(self):
        assert is_retryable_order_error(Exception("Order rejected")) is False

    def test_insufficient_funds_is_not_retryable(self):
        assert is_retryable_order_error(Exception("Insufficient buying power")) is False

    def test_invalid_symbol_is_not_retryable(self):
        assert is_retryable_order_error(Exception("Invalid symbol XYZ")) is False

    def test_network_error_is_retryable(self):
        assert is_retryable_order_error(ConnectionError("timeout")) is True

    def test_generic_error_is_retryable(self):
        assert is_retryable_order_error(Exception("Something went wrong")) is True


class TestRetryDecorator:
    """Tests for retry decorator."""

    def test_success_on_first_attempt(self):
        @retry(max_attempts=3, base_delay=0.01)
        def success_func():
            return "success"

        assert success_func() == "success"

    def test_success_after_retries(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, jitter=False)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("timeout")
            return "success"

        assert flaky_func() == "success"
        assert call_count == 3

    def test_failure_after_max_attempts(self):
        @retry(max_attempts=2, base_delay=0.01, jitter=False)
        def always_fails():
            raise ConnectionError("always fails")

        with pytest.raises(ConnectionError):
            always_fails()

    def test_non_retryable_error_raises_immediately(self):
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def non_retryable():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            non_retryable()
        assert call_count == 1


class TestUtcNow:
    """Tests for utc_now."""

    def test_returns_utc_datetime(self):
        now = utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc

    def test_returns_recent_time(self):
        now = utc_now()
        assert now.year >= 2024


class TestToUtc:
    """Tests for to_utc."""

    def test_naive_datetime_assumed_utc(self):
        naive = datetime(2024, 1, 15, 12, 0, 0)
        result = to_utc(naive)
        assert result.tzinfo == timezone.utc
        assert result.hour == 12

    def test_aware_datetime_converted(self):
        et_offset = timezone(timedelta(hours=-5))
        et_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=et_offset)
        result = to_utc(et_time)
        assert result.tzinfo == timezone.utc
        assert result.hour == 17  # 12 ET = 17 UTC

    def test_utc_datetime_unchanged(self):
        utc_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = to_utc(utc_time)
        assert result.hour == 12


class TestParseDatetime:
    """Tests for parse_datetime."""

    def test_parse_iso_string(self):
        result = parse_datetime("2024-01-15T12:00:00+00:00")
        assert result is not None
        assert result.year == 2024
        assert result.hour == 12

    def test_parse_iso_string_z(self):
        result = parse_datetime("2024-01-15T12:00:00Z")
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_parse_unix_timestamp(self):
        result = parse_datetime(1705320000)  # 2024-01-15T12:00:00Z
        assert result is not None
        assert result.year == 2024

    def test_parse_milliseconds(self):
        result = parse_datetime(1705320000000)  # Milliseconds
        assert result is not None
        assert result.year == 2024

    def test_parse_unix_string(self):
        result = parse_datetime("1705320000")
        assert result is not None
        assert result.year == 2024

    def test_parse_datetime_object(self):
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_datetime(dt)
        assert result is not None
        assert result == dt

    def test_parse_none(self):
        result = parse_datetime(None)
        assert result is None

    def test_parse_invalid_string(self):
        result = parse_datetime("not a date")
        assert result is None


class TestIsMarketOpen:
    """Tests for is_market_open."""

    def test_market_closed_weekend(self):
        # Saturday
        saturday = datetime(2024, 1, 13, 15, 0, 0, tzinfo=timezone.utc)
        assert is_market_open(saturday) is False

    def test_market_closed_sunday(self):
        # Sunday
        sunday = datetime(2024, 1, 14, 15, 0, 0, tzinfo=timezone.utc)
        assert is_market_open(sunday) is False

    def test_market_open_weekday(self):
        # Tuesday 15:00 UTC = 10:00 AM ET (during market hours)
        tuesday = datetime(2024, 1, 16, 15, 0, 0, tzinfo=timezone.utc)
        assert is_market_open(tuesday) is True

    def test_market_closed_before_hours(self):
        # Tuesday 13:00 UTC = 8:00 AM ET (before market opens at 9:30)
        tuesday = datetime(2024, 1, 16, 13, 0, 0, tzinfo=timezone.utc)
        assert is_market_open(tuesday) is False

    def test_market_closed_after_hours(self):
        # Tuesday 21:30 UTC = 4:30 PM ET (after market closes at 4:00)
        tuesday = datetime(2024, 1, 16, 21, 30, 0, tzinfo=timezone.utc)
        assert is_market_open(tuesday) is False
