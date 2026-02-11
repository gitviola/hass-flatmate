"""Sensor platform for hass_flatmate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import HassFlatmateCoordinatorEntity, get_runtime


def _member_lookup(data: Mapping[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for member in data.get("members", []):
        if member.get("id") is not None:
            result[int(member["id"])] = member.get("display_name", str(member["id"]))
    return result


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
        return {
            "recent": events[:20],
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
            CleaningCurrentAssigneeSensor(entry, runtime),
            CleaningCurrentStatusSensor(entry, runtime),
            CleaningNextAssigneeSensor(entry, runtime),
            ActivityRecentSensor(entry, runtime),
        ]
    )
