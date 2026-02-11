"""Date and time helper functions for weekly rotation logic."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def week_start_for(dt: datetime) -> date:
    """Return Monday date for the provided datetime."""

    return (dt.date() - timedelta(days=dt.weekday()))


def monday_for(day: date) -> date:
    """Return Monday date for the provided day."""

    return day - timedelta(days=day.weekday())


def add_weeks(week_start: date, weeks: int) -> date:
    return week_start + timedelta(days=weeks * 7)
