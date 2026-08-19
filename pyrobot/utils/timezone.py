"""Timezone utilities for consistent UTC handling across the platform.

All internal datetimes should be UTC. Use these utilities to convert
to/from market timezones when needed.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional


# Common US market timezone offsets
ET_OFFSET = timedelta(hours=-5)  # EST (standard time)
EDT_OFFSET = timedelta(hours=-4)  # EDT (daylight saving)
CT_OFFSET = timedelta(hours=-6)  # CST
MT_OFFSET = timedelta(hours=-7)  # MST
PT_OFFSET = timedelta(hours=-8)  # PST


def utc_now() -> datetime:
    """Get current time in UTC with timezone info.

    Returns:
        Current UTC datetime with timezone info.
    """
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Convert a datetime to UTC.

    If the datetime is naive (no timezone info), it's assumed to be UTC.

    Args:
        dt: Datetime to convert.

    Returns:
        Timezone-aware UTC datetime.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_market_time(dt: datetime, market: str = "US/EASTERN") -> datetime:
    """Convert UTC datetime to market timezone.

    Args:
        dt: UTC datetime.
        market: Market identifier (currently only 'US/EASTERN' supported).

    Returns:
        Market-timezone datetime.
    """
    dt_utc = to_utc(dt)

    if market.upper() in ("US/EASTERN", "ET", "EST", "EDT"):
        # Simple EST/EDT approximation (real implementation would use pytz/zoneinfo)
        # For production, use: from zoneinfo import ZoneInfo
        # return dt_utc.astimezone(ZoneInfo("America/New_York"))
        offset = _get_us_eastern_offset(dt_utc)
        return dt_utc.astimezone(timezone(offset))
    else:
        # Default to UTC
        return dt_utc


def _get_us_eastern_offset(dt: datetime) -> timedelta:
    """Get US Eastern timezone offset (approximation).

    DST: Second Sunday in March to First Sunday in November.
    This is a simplified version; use zoneinfo in production.
    """
    year = dt.year
    # DST starts second Sunday of March
    march_first = datetime(year, 3, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - march_first.weekday()) % 7
    second_sunday = march_first + timedelta(days=days_to_sun + 7)
    dst_start = second_sunday.replace(hour=7)  # 2 AM EST = 7 AM UTC

    # DST ends first Sunday of November
    november_first = datetime(year, 11, 1, tzinfo=timezone.utc)
    days_to_sun = (6 - november_first.weekday()) % 7
    first_sunday = november_first + timedelta(days=days_to_sun)
    dst_end = first_sunday.replace(hour=6)  # 2 AM EDT = 6 AM UTC

    if dst_start <= dt < dst_end:
        return EDT_OFFSET  # DST active
    else:
        return ET_OFFSET  # Standard time


def is_market_open(dt: Optional[datetime] = None, market: str = "US/EASTERN") -> bool:
    """Check if the US stock market is open.

    Args:
        dt: Datetime to check (UTC). Uses current time if None.
        market: Market identifier.

    Returns:
        True if market is open, False otherwise.
    """
    if dt is None:
        dt = utc_now()

    market_dt = to_market_time(dt, market)

    # Check if it's a weekday (Monday=0, Friday=4)
    if market_dt.weekday() > 4:
        return False

    # Check market hours (9:30 AM - 4:00 PM ET)
    market_open = market_dt.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = market_dt.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= market_dt <= market_close


def parse_datetime(dt_value) -> Optional[datetime]:
    """Parse various datetime formats to UTC datetime.

    Handles:
    - ISO format strings
    - Unix timestamps (seconds or milliseconds)
    - Existing datetime objects

    Args:
        dt_value: Value to parse.

    Returns:
        UTC datetime or None if parsing fails.
    """
    if dt_value is None:
        return None

    if isinstance(dt_value, datetime):
        return to_utc(dt_value)

    if isinstance(dt_value, (int, float)):
        # Detect if milliseconds (>1e12) or seconds
        if dt_value > 1e12:
            dt_value = dt_value / 1000.0
        return datetime.fromtimestamp(dt_value, tz=timezone.utc)

    if isinstance(dt_value, str):
        try:
            # Try ISO format
            dt = datetime.fromisoformat(dt_value.replace("Z", "+00:00"))
            return to_utc(dt)
        except (ValueError, TypeError):
            pass

        try:
            # Try Unix timestamp string
            ts = float(dt_value)
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, TypeError):
            pass

    return None
