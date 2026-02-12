"""Sensor platform for hass_flatmate."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SERVICE_ADD_FAVORITE_ITEM,
    SERVICE_ADD_SHOPPING_ITEM,
    SERVICE_MARK_CLEANING_DONE,
    SERVICE_MARK_CLEANING_TAKEOVER_DONE,
    SERVICE_MARK_CLEANING_UNDONE,
    SERVICE_SWAP_CLEANING_WEEK,
    SERVICE_COMPLETE_SHOPPING_ITEM,
    SERVICE_DELETE_SHOPPING_ITEM,
    SERVICE_DELETE_FAVORITE_ITEM,
)
from .entity import HassFlatmateCoordinatorEntity, get_runtime


def _member_lookup(data: Mapping[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for member in data.get("members", []):
        if member.get("id") is not None:
            result[int(member["id"])] = member.get("display_name", str(member["id"]))
    return result


def _parse_datetime_local(value: Any) -> datetime | None:
    if value is None:
        return None
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = dt_util.as_utc(parsed)
    return dt_util.as_local(parsed)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _activity_summary(row: Mapping[str, Any], members: Mapping[int, str]) -> str:
    action = str(row.get("action", ""))
    payload = row.get("payload_json", {})
    if not isinstance(payload, Mapping):
        payload = {}

    actor_name = None
    actor_id = row.get("actor_member_id")
    if actor_id is not None:
        try:
            actor_name = members.get(int(actor_id))
        except (TypeError, ValueError):
            actor_name = None

    if action == "shopping_item_added":
        item_name = str(payload.get("name", "item"))
        return f"{actor_name or 'Someone'} added {item_name}"
    if action == "shopping_item_completed":
        item_name = str(payload.get("name", "item"))
        return f"{actor_name or 'Someone'} bought {item_name}"
    if action == "shopping_item_deleted":
        item_name = str(payload.get("name", "item"))
        return f"{actor_name or 'Someone'} removed {item_name}"
    if action == "cleaning_done":
        return f"{actor_name or 'Someone'} marked cleaning as done"
    if action == "cleaning_takeover_done":
        return f"{actor_name or 'Someone'} completed a cleaning takeover"
    if action == "cleaning_swap_created":
        return "A cleaning swap was created"
    if action == "cleaning_swap_canceled":
        return "A cleaning swap was canceled"
    if action == "cleaning_override_auto_canceled_member_inactive":
        return "A cleaning override was canceled because a flatmate left"
    if action in {"manual_import_applied", "flatastic_import_applied"}:
        return "Manual data import applied"
    return action.replace("_", " ")


class ShoppingOpenCountSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Shopping Open Count"
    _attr_unique_id = "hass_flatmate_shopping_open_count"
    _attr_icon = "mdi:cart-outline"

    @property
    def native_value(self) -> int:
        items = self.coordinator.data.get("shopping_items", [])
        return sum(1 for item in items if item.get("status") == "open")


class ShoppingDistributionSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Shopping Distribution 90d"
    _attr_unique_id = "hass_flatmate_shopping_distribution_90d"
    _attr_icon = "mdi:chart-bar"

    @property
    def native_value(self) -> int:
        stats = self.coordinator.data.get("shopping_stats", {})
        return int(stats.get("total_completed", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.data.get("shopping_stats", {})
        return {
            "window_days": int(stats.get("window_days", 90)),
            "total_completed": int(stats.get("total_completed", 0)),
            "unknown_excluded_count": int(stats.get("unknown_excluded_count", 0)),
            "distribution": stats.get("distribution", []),
            "svg_render_version": stats.get("svg_render_version", ""),
        }


class ShoppingDataSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Shopping Data"
    _attr_unique_id = "hass_flatmate_shopping_data"
    _attr_icon = "mdi:format-list-bulleted-square"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        items = self.coordinator.data.get("shopping_items", [])
        return sum(1 for item in items if item.get("status") == "open")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        members = _member_lookup(self.coordinator.data)
        open_items: list[dict[str, Any]] = []

        for item in self.coordinator.data.get("shopping_items", []):
            if item.get("status") != "open":
                continue

            added_at_raw = item.get("added_at")
            added_at = _parse_datetime_local(added_at_raw)
            added_at_local = added_at.isoformat() if isinstance(added_at, datetime) else None

            added_by_member_id = item.get("added_by_member_id")
            added_by_name = None
            if added_by_member_id is not None:
                try:
                    added_by_name = members.get(int(added_by_member_id))
                except (TypeError, ValueError):
                    added_by_name = None

            open_items.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "added_at": added_at_local or added_at_raw,
                    "added_by_member_id": added_by_member_id,
                    "added_by_name": added_by_name,
                }
            )

        open_items.sort(
            key=lambda row: (
                str(row.get("added_at") or ""),
                str(row.get("name") or "").lower(),
            )
        )

        favorites = [
            {"id": item.get("id"), "name": item.get("name")}
            for item in self.coordinator.data.get("shopping_favorites", [])
            if item.get("id") is not None and item.get("name")
        ]
        favorites.sort(key=lambda row: str(row["name"]).lower())

        recents = [str(item) for item in self.coordinator.data.get("shopping_recents", []) if item]
        suggestions = []
        seen: set[str] = set()
        for name in recents:
            key = str(name).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            suggestions.append(name)

        return {
            "open_items": open_items,
            "favorites": favorites,
            "recents": recents,
            "suggestions": suggestions[:40],
            "service_domain": DOMAIN,
            "service_add_item": SERVICE_ADD_SHOPPING_ITEM,
            "service_complete_item": SERVICE_COMPLETE_SHOPPING_ITEM,
            "service_delete_item": SERVICE_DELETE_SHOPPING_ITEM,
            "service_add_favorite": SERVICE_ADD_FAVORITE_ITEM,
            "service_delete_favorite": SERVICE_DELETE_FAVORITE_ITEM,
        }


class CleaningCurrentAssigneeSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Current Assignee"
    _attr_unique_id = "hass_flatmate_cleaning_current_assignee"
    _attr_icon = "mdi:broom"

    @property
    def native_value(self) -> str | None:
        current = self.coordinator.data.get("cleaning_current", {})
        member_id = current.get("effective_assignee_member_id")
        if member_id is None:
            return None
        return _member_lookup(self.coordinator.data).get(int(member_id), f"Member {member_id}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self.coordinator.data.get("cleaning_current", {})
        return {
            "week_start": current.get("week_start"),
            "effective_assignee_member_id": current.get("effective_assignee_member_id"),
            "baseline_assignee_member_id": current.get("baseline_assignee_member_id"),
        }


class CleaningCurrentStatusSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Current Week Status"
    _attr_unique_id = "hass_flatmate_cleaning_current_week_status"
    _attr_icon = "mdi:check-decagram-outline"

    @property
    def native_value(self) -> str | None:
        current = self.coordinator.data.get("cleaning_current", {})
        status = current.get("status")
        return str(status) if status is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self.coordinator.data.get("cleaning_current", {})
        return {
            "week_start": current.get("week_start"),
            "completed_by_member_id": current.get("completed_by_member_id"),
        }


class CleaningNextAssigneeSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Next Assignee"
    _attr_unique_id = "hass_flatmate_cleaning_next_assignee"
    _attr_icon = "mdi:calendar-next"

    @property
    def native_value(self) -> str | None:
        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        if len(schedule) < 2:
            return None
        member_id = schedule[1].get("effective_assignee_member_id")
        if member_id is None:
            return None
        return _member_lookup(self.coordinator.data).get(int(member_id), f"Member {member_id}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        if len(schedule) < 2:
            return {}
        row = schedule[1]
        return {
            "week_start": row.get("week_start"),
            "effective_assignee_member_id": row.get("effective_assignee_member_id"),
            "baseline_assignee_member_id": row.get("baseline_assignee_member_id"),
            "override_type": row.get("override_type"),
        }


class CleaningScheduleSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Schedule"
    _attr_unique_id = "hass_flatmate_cleaning_schedule"
    _attr_icon = "mdi:calendar-range"

    @property
    def native_value(self) -> int:
        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        return len(schedule)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        members = _member_lookup(self.coordinator.data)
        members_payload = [
            {
                "member_id": int(member.get("id")),
                "name": member.get("display_name"),
                "ha_user_id": member.get("ha_user_id"),
            }
            for member in self.coordinator.data.get("members", [])
            if member.get("id") is not None and member.get("display_name") and member.get("active", True)
        ]
        members_payload.sort(key=lambda row: str(row["name"]).lower())

        member_user_lookup: dict[int, str | None] = {}
        for member in self.coordinator.data.get("members", []):
            if member.get("id") is None:
                continue
            if not member.get("active", True):
                continue
            try:
                member_id = int(member.get("id"))
            except (TypeError, ValueError):
                continue
            user_id = member.get("ha_user_id")
            member_user_lookup[member_id] = str(user_id) if user_id is not None else None

        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        current = self.coordinator.data.get("cleaning_current", {})
        current_week_start = str(current.get("week_start") or "")
        current_week_start_date = _parse_date(current_week_start)
        current_status = current.get("status")
        current_completed_by_id = current.get("completed_by_member_id")

        weeks = []
        for row in schedule:
            week_start = _parse_date(row.get("week_start"))
            if week_start is None:
                continue

            week_end = week_start + timedelta(days=6)
            effective_id = row.get("effective_assignee_member_id")
            baseline_id = row.get("baseline_assignee_member_id")
            override_type = row.get("override_type")
            override_source = row.get("override_source")

            assignee_name = None
            baseline_name = None
            if effective_id is not None:
                try:
                    assignee_name = members.get(int(effective_id))
                except (TypeError, ValueError):
                    assignee_name = None
            if baseline_id is not None:
                try:
                    baseline_name = members.get(int(baseline_id))
                except (TypeError, ValueError):
                    baseline_name = None

            note = ""
            if override_type == "manual_swap":
                note = "swap"
            elif override_type == "compensation":
                note = "swap return week" if override_source == "manual" else "make-up shift"

            is_current = week_start.isoformat() == current_week_start
            status_value = row.get("status")
            if status_value is None and is_current:
                status_value = current_status

            completed_by_member_id = row.get("completed_by_member_id")
            if completed_by_member_id is None and is_current:
                completed_by_member_id = current_completed_by_id

            completed_by_name = None
            if completed_by_member_id is not None:
                try:
                    completed_by_name = members.get(int(completed_by_member_id))
                except (TypeError, ValueError):
                    completed_by_name = None

            is_past = (
                current_week_start_date is not None
                and week_start < current_week_start_date
            )
            is_previous = (
                current_week_start_date is not None
                and week_start == (current_week_start_date - timedelta(days=7))
            )
            is_next = (
                current_week_start_date is not None
                and week_start == (current_week_start_date + timedelta(days=7))
            )
            assignee_user_id = None
            if effective_id is not None:
                try:
                    assignee_user_id = member_user_lookup.get(int(effective_id))
                except (TypeError, ValueError):
                    assignee_user_id = None
            original_assignee_user_id = None
            if baseline_id is not None:
                try:
                    original_assignee_user_id = member_user_lookup.get(int(baseline_id))
                except (TypeError, ValueError):
                    original_assignee_user_id = None
            weeks.append(
                {
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "week_number": week_start.isocalendar().week,
                    "assignee_member_id": effective_id,
                    "assignee_name": assignee_name,
                    "assignee_user_id": assignee_user_id,
                    "original_assignee_member_id": baseline_id,
                    "original_assignee_name": baseline_name,
                    "original_assignee_user_id": original_assignee_user_id,
                    "baseline_assignee_member_id": baseline_id,
                    "baseline_assignee_name": baseline_name,
                    "override_type": override_type,
                    "override_source": override_source,
                    "note": note,
                    "is_current": is_current,
                    "is_past": is_past,
                    "is_previous": is_previous,
                    "is_next": is_next,
                    "status": status_value,
                    "completed_by_member_id": completed_by_member_id,
                    "completed_by_name": completed_by_name,
                    "completion_mode": row.get("completion_mode"),
                }
            )

        return {
            "weeks": weeks,
            "members": members_payload,
            "service_domain": DOMAIN,
            "service_mark_done": SERVICE_MARK_CLEANING_DONE,
            "service_mark_undone": SERVICE_MARK_CLEANING_UNDONE,
            "service_mark_takeover_done": SERVICE_MARK_CLEANING_TAKEOVER_DONE,
            "service_swap_week": SERVICE_SWAP_CLEANING_WEEK,
        }


class ActivityRecentSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Activity Recent"
    _attr_unique_id = "hass_flatmate_activity_recent"
    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        events = self.coordinator.data.get("activity", [])
        return len(events)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        events = self.coordinator.data.get("activity", [])
        members = _member_lookup(self.coordinator.data)
        human = []
        for row in events[:20]:
            if not isinstance(row, Mapping):
                continue
            created = _parse_datetime_local(row.get("created_at"))
            human.append(
                {
                    "id": row.get("id"),
                    "created_at": created.isoformat() if created else row.get("created_at"),
                    "summary": _activity_summary(row, members),
                    "action": row.get("action"),
                }
            )
        return {
            "recent": events[:20],
            "recent_human": human,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)

    async_add_entities(
        [
            ShoppingOpenCountSensor(entry, runtime),
            ShoppingDistributionSensor(entry, runtime),
            ShoppingDataSensor(entry, runtime),
            CleaningCurrentAssigneeSensor(entry, runtime),
            CleaningCurrentStatusSensor(entry, runtime),
            CleaningNextAssigneeSensor(entry, runtime),
            CleaningScheduleSensor(entry, runtime),
            ActivityRecentSensor(entry, runtime),
        ]
    )
