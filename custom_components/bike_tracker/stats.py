"""Calendar period helpers for the statistics sensors."""

from __future__ import annotations

from datetime import datetime, timedelta

from .const import PERIOD_MONTH, PERIOD_TODAY, PERIOD_TOTAL, PERIOD_WEEK, PERIOD_YEAR


def period_bounds(period: str, now: datetime) -> tuple[float | None, float | None]:
    """Return (start_ts, end_ts) for a named period, in local calendar terms.

    ``now`` must be timezone aware and in the user's local timezone so that
    "today" means their day, not UTC's.
    """
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if period == PERIOD_TODAY:
        start = midnight
    elif period == PERIOD_WEEK:
        # ISO week: Monday is day 0.
        start = midnight - timedelta(days=midnight.weekday())
    elif period == PERIOD_MONTH:
        start = midnight.replace(day=1)
    elif period == PERIOD_YEAR:
        start = midnight.replace(month=1, day=1)
    elif period == PERIOD_TOTAL:
        return None, None
    else:
        raise ValueError(f"Unknown period: {period}")

    return start.timestamp(), None


def rolling_window(now: datetime, days: int) -> tuple[float, float]:
    """Return (start_ts, end_ts) for the last ``days`` calendar days."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = midnight + timedelta(days=1)
    start = end - timedelta(days=days)
    return start.timestamp(), end.timestamp()
