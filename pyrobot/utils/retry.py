"""Retry policy with exponential backoff for transient errors."""

import time

from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

from pyrobot.logging_config import get_logger

logger = get_logger("retry")

# Default retryable exception types
RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# HTTP status codes that are retryable
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def is_retryable_exception(exc: Exception) -> bool:
    """Check if an exception is retryable.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception is retryable, False otherwise.
    """
    exc_type = type(exc)

    # Check if it's a known retryable type
    if exc_type in RETRYABLE_EXCEPTIONS:
        return True

    # Check for HTTP-like status codes on exception attributes
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code is not None and status_code in RETRYABLE_STATUS_CODES:
        return True

    # Check for timeout-related messages
    exc_str = str(exc).lower()
    timeout_keywords = ("timeout", "timed out", "connection refused", "connection reset")
    if any(keyword in exc_str for keyword in timeout_keywords):
        return True

    return False


def is_retryable_order_error(exc: Exception) -> bool:
    """Check if an order error is retryable.

    Order errors like 'rejected', 'invalid', 'insufficient funds'
    should NOT be retried.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception is retryable, False otherwise.
    """
    non_retryable_keywords = (
        "rejected",
        "invalid",
        "insufficient",
        "not enough",
        "denied",
        "forbidden",
        "unauthorized",
        "symbol not found",
        "invalid symbol",
    )

    exc_str = str(exc).lower()
    return not any(keyword in exc_str for keyword in non_retryable_keywords)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_check: Optional[Callable[[Exception], bool]] = None,
):
    """Decorator for retrying function calls with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (total calls = max_attempts + 1).
        base_delay: Base delay in seconds between retries.
        max_delay: Maximum delay in seconds between retries.
        exponential_base: Base for exponential backoff calculation.
        jitter: Whether to add random jitter to delay.
        retryable_check: Custom function to check if an exception is retryable.
                         Defaults to is_retryable_exception.

    Returns:
        Decorated function.

    Example:
        @retry(max_attempts=3, base_delay=1.0)
        def fetch_data(url):
            return requests.get(url)
    """
    if retryable_check is None:
        retryable_check = is_retryable_exception

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exception = exc

                    if attempt >= max_attempts:
                        logger.error(
                            f"All {max_attempts + 1} attempts failed for "
                            f"{func.__name__}: {exc}"
                        )
                        raise

                    if not retryable_check(exc):
                        logger.warning(
                            f"Non-retryable error on attempt {attempt + 1} "
                            f"for {func.__name__}: {exc}"
                        )
                        raise

                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay,
                    )

                    if jitter:
                        import random
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"Retryable error on attempt {attempt + 1}/{max_attempts + 1} "
                        f"for {func.__name__}: {exc}. "
                        f"Retrying in {delay:.2f}s..."
                    )

                    time.sleep(delay)

            raise last_exception  # Should not reach here, but just in case

        return wrapper

    return decorator
