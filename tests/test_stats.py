"""Tests for the calendar period helpers."""

from datetime import datetime, timezone

import pytest
from bt.stats import period_bounds, rolling_window

# Wednesday, 2026-08-12 14:30 timezone.utc
NOW = datetime(2026, 8, 12, 14, 30, tzinfo=timezone.utc)


def test_today_starts_at_midnight():
    start, end = period_bounds("today", NOW)
    assert datetime.fromtimestamp(start, timezone.utc).hour == 0
    assert end is None


def test_week_starts_on_monday():
    start, _ = period_bounds("week", NOW)
    monday = datetime.fromtimestamp(start, timezone.utc)
    assert monday.weekday() == 0
    assert monday.day == 10


def test_month_and_year():
    assert datetime.fromtimestamp(period_bounds("month", NOW)[0], timezone.utc).day == 1
    year_start = datetime.fromtimestamp(period_bounds("year", NOW)[0], timezone.utc)
    assert (year_start.month, year_start.day) == (1, 1)


def test_total_is_unbounded():
    assert period_bounds("total", NOW) == (None, None)


def test_unknown_period():
    with pytest.raises(ValueError):
        period_bounds("decade", NOW)


def test_rolling_window_covers_n_days():
    start, end = rolling_window(NOW, 7)
    assert round((end - start) / 86400) == 7
