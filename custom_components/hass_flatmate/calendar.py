"""Calendar platform for hass_flatmate activity."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import HassFlatmateCoordinatorEntity, get_runtime


def _build_event_summary(item: dict) -> str | None:
    action = item.get("action")
    payload = item.get("payload_json", {})

    if action == "shopping_item_completed":
        name = payload.get("name", "item")
        return f"Shopping completed: {name}"
    if action == "cleaning_done":
        return "Cleaning completed"
    if action == "cleaning_takeover_done":
        return "Cleaning completed (takeover)"
    return None


def _parse_event(item: dict) -> CalendarEvent | None:
    created = item.get("created_at")
    if not created:
        return None
    parsed = dt_util.parse_datetime(str(created))
    if parsed is None:
        return None

    summary = _build_event_summary(item)
    if summary is None:
        return None

    start = parsed
    end = start + timedelta(minutes=15)
    return CalendarEvent(
        summary=summary,
        start=start,
        end=end,
        description=item.get("action", ""),
    )


class HassFlatmateActivityCalendar(HassFlatmateCoordinatorEntity, CalendarEntity):
    """Calendar entity exposing shopping/cleaning completion events."""

    _attr_name = "Activity"
    _attr_unique_id = "hass_flatmate_activity"

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        future = [event for event in self._events() if event.end >= now]
        future.sort(key=lambda event: event.start)
        return future[0] if future else None

    def _events(self) -> list[CalendarEvent]:
        rows = self.coordinator.data.get("activity", [])
        events = []
        for row in rows:
            event = _parse_event(row)
            if event is not None:
                events.append(event)
        return events

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        del hass
        events = []
        for event in self._events():
            if event.end >= start_date and event.start <= end_date:
                events.append(event)
        events.sort(key=lambda item: item.start)
        return events


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)
    async_add_entities([HassFlatmateActivityCalendar(entry, runtime)])
