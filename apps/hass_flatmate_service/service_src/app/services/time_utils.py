"""Date and time helper functions for weekly rotation logic."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..settings import settings

# Home Assistant's time zone for the current request, sent by the integration
# in the ``X-Flatmate-Timezone`` header. Timestamps are stored in UTC, but week
# and calendar-day boundaries must follow the flat's local midnight (incl. DST).
_request_timezone: ContextVar[tzinfo | None] = ContextVar("hass_flatmate_request_timezone", default=None)


def parse_timezone(name: str | None) -> tzinfo | None:
    if not name or not name.strip():
        return None
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError):
        return None


def local_timezone() -> tzinfo:
    """Time zone for week/day boundaries: request header, then env, then UTC."""

    return _request_timezone.get() or parse_timezone(settings.timezone) or timezone.utc


@contextmanager
def use_timezone(tz: tzinfo | None) -> Iterator[None]:
    token = _request_timezone.set(tz)
    try:
        yield
    finally:
        _request_timezone.reset(token)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def local_date(dt: datetime) -> date:
    """Calendar date of ``dt`` in the local time zone (naive values are taken as UTC)."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(local_timezone()).date()


def week_start_for(dt: datetime) -> date:
    """Return the local Monday date for the provided datetime."""

    day = local_date(dt)
    return day - timedelta(days=day.weekday())


def monday_for(day: date) -> date:
    """Return Monday date for the provided day."""

    return day - timedelta(days=day.weekday())


def add_weeks(week_start: date, weeks: int) -> date:
    return week_start + timedelta(days=weeks * 7)
