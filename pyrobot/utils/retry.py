"""Retry policy with exponential backoff integrated with the platform's exception hierarchy.

Retryable errors (automatically retried):
    BrokerRateLimitError, BrokerTimeoutError, BrokerConnectionError
    ConnectionError, TimeoutError, OSError
    HTTP 429 / 500 / 502 / 503 / 504

Non-retryable errors (never retried):
    OrderRejectedError, InvalidSymbolError, AuthenticationError,
    KillSwitchError, DuplicateOrderError
"""

import random
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

# Keyword fragments in exception messages that indicate non-retryable errors
_NON_RETRYABLE_KEYWORDS: Tuple[str, ...] = (
    "rejected",
    "invalid",
    "insufficient",
    "not enough",
    "denied",
    "forbidden",
    "unauthorized",
    "symbol not found",
    "invalid symbol",
    "kill switch",
    "duplicate order",
)


def is_retryable_exception(exc: Exception) -> bool:
    """Return True if the exception is safe to retry automatically.

    Uses the platform's exception hierarchy first, then falls back to
    heuristics based on HTTP status codes and message keywords.

    Args:
        exc: The exception to classify.

    Returns:
        True if the exception is retryable, False otherwise.
    """
    from pyrobot.exceptions import (
        NON_RETRYABLE_EXCEPTIONS as DOMAIN_NON_RETRYABLE,
    )
    from pyrobot.exceptions import (
        RETRYABLE_EXCEPTIONS as DOMAIN_RETRYABLE,
    )

    # Platform-level: non-retryable takes priority
    if isinstance(exc, DOMAIN_NON_RETRYABLE):
        return False

    # Platform-level: retryable
    if isinstance(exc, DOMAIN_RETRYABLE):
        return True

    # Standard OS / network errors
    if isinstance(exc, RETRYABLE_EXCEPTIONS):
        return True

    # Check for HTTP-like status codes on exception attributes
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code in RETRYABLE_STATUS_CODES:
        return True

    # Keyword-based heuristics in exception message
    exc_str = str(exc).lower()
    if any(kw in exc_str for kw in _NON_RETRYABLE_KEYWORDS):
        return False

    timeout_keywords = ("timeout", "timed out", "connection refused", "connection reset")
    if any(kw in exc_str for kw in timeout_keywords):
        return True

    return False


def is_retryable_order_error(exc: Exception) -> bool:
    """Stricter retryability check for order-related errors.

    Order errors like 'rejected', 'invalid symbol', 'insufficient funds'
    must NEVER be retried — they would only waste time and risk duplicate fills.
    Generic / transient network errors are permitted.

    Args:
        exc: The exception to check.

    Returns:
        True if not explicitly non-retryable, False otherwise.
    """
    from pyrobot.exceptions import NON_RETRYABLE_EXCEPTIONS as DOMAIN_NON_RETRYABLE

    if isinstance(exc, DOMAIN_NON_RETRYABLE):
        return False

    exc_str = str(exc).lower()
    if any(kw in exc_str for kw in _NON_RETRYABLE_KEYWORDS):
        return False

    return True


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_check: Optional[Callable[[Exception], bool]] = None,
):
    """Decorator that retries a function call with exponential back-off.

    Args:
        max_attempts: Maximum number of additional retry attempts after the
            first call. Total call count = max_attempts + 1.
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Upper bound on the inter-retry delay in seconds.
        exponential_base: Multiplier for each successive retry delay.
        jitter: If True, multiply the computed delay by a random factor in
            [0.5, 1.5] to spread concurrent retries.
        retryable_check: Custom function ``(exc) -> bool`` that decides
            whether an exception should trigger a retry.
            Defaults to :func:`is_retryable_exception`.

    Returns:
        Decorated callable.
    """
    _check = retryable_check or is_retryable_exception

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None

            for attempt in range(max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc

                    if attempt >= max_attempts:
                        logger.error(
                            "All %d attempt(s) exhausted for %s: %s",
                            max_attempts + 1,
                            func.__qualname__,
                            exc,
                        )
                        raise

                    if not _check(exc):
                        logger.warning(
                            "Non-retryable error on attempt %d/%d for %s: %s",
                            attempt + 1,
                            max_attempts + 1,
                            func.__qualname__,
                            exc,
                        )
                        raise

                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    if jitter:
                        delay *= 0.5 + random.random()  # [0.5, 1.5] × delay

                    logger.warning(
                        "Retryable error (attempt %d/%d) for %s: %s — "
                        "retrying in %.2fs",
                        attempt + 1,
                        max_attempts + 1,
                        func.__qualname__,
                        exc,
                        delay,
                    )
                    time.sleep(delay)

            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
