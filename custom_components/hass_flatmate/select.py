"""Select platform for hass_flatmate."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID,
    CONF_NOTIFICATION_TEST_MODE,
    CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID,
    CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID,
    DEFAULT_NOTIFICATION_TEST_MODE,
)
from .entity import HassFlatmateCoordinatorEntity, get_runtime

UNSET_OPTION = "Not set"


def _coerce_member_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _select_options(runtime) -> tuple[list[str], dict[str, int]]:
    entries: list[tuple[str, int]] = []
    for member in runtime.coordinator.data.get("members", []):
        if not isinstance(member, dict):
            continue
        if not member.get("active", True):
            continue
        notify_service = member.get("notify_service")
        if not isinstance(notify_service, str) or not notify_service:
            continue
        member_id = _coerce_member_id(member.get("id"))
        if member_id is None:
            continue
        display = str(member.get("display_name", member_id))
        entries.append((f"{display} (#{member_id})", member_id))

    entries.sort(key=lambda item: item[0].lower())
    labels = [UNSET_OPTION] + [label for label, _ in entries]
    mapping = {label: member_id for label, member_id in entries}
    return labels, mapping


async def _persist_options(entity: HassFlatmateCoordinatorEntity) -> None:
    options = {
        **entity.config_entry.options,
        CONF_NOTIFICATION_TEST_MODE: bool(
            entity.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_MODE, DEFAULT_NOTIFICATION_TEST_MODE)
        ),
        CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID: _coerce_member_id(
            entity.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID)
        ),
        CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID: entity.runtime.runtime_state.get(
            CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID
        ),
        CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID: entity.runtime.runtime_state.get(
            CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID
        ),
    }
    entity.hass.config_entries.async_update_entry(entity.config_entry, options=options)


def _calendar_select_options(hass: HomeAssistant) -> tuple[list[str], dict[str, str]]:
    entries: list[tuple[str, str]] = []
    for state in hass.states.async_all("calendar"):
        entity_id = state.entity_id
        if entity_id == "calendar.hass_flatmate_activity":
            continue
        display_name = str(state.name or entity_id)
        entries.append((f"{display_name} ({entity_id})", entity_id))

    entries.sort(key=lambda item: item[0].lower())
    labels = [UNSET_OPTION] + [label for label, _ in entries]
    mapping = {label: entity_id for label, entity_id in entries}
    return labels, mapping


class NotificationTestTargetSelect(HassFlatmateCoordinatorEntity, SelectEntity):
    """Select target recipient for notification test mode."""

    _attr_name = "Notification Test Target"
    _attr_unique_id = "hass_flatmate_notification_test_target"
    _attr_icon = "mdi:account-arrow-right"

    def _labels_mapping(self) -> tuple[list[str], dict[str, int]]:
        return _select_options(self.runtime)

    @property
    def options(self) -> list[str]:
        labels, _mapping = self._labels_mapping()
        return labels

    @property
    def current_option(self) -> str | None:
        labels, mapping = self._labels_mapping()
        target_member_id = _coerce_member_id(
            self.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID)
        )
        if target_member_id is None:
            return UNSET_OPTION
        for label, member_id in mapping.items():
            if member_id == target_member_id:
                return label
        return UNSET_OPTION if UNSET_OPTION in labels else None

    async def async_select_option(self, option: str) -> None:
        labels, mapping = self._labels_mapping()
        if option not in labels:
            raise ValueError(f"Invalid option: {option}")

        if option == UNSET_OPTION:
            self.runtime.runtime_state[CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID] = None
        else:
            self.runtime.runtime_state[CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID] = mapping[option]

        await _persist_options(self)
        self.async_write_ha_state()


class _CalendarTargetSelectBase(HassFlatmateCoordinatorEntity, SelectEntity):
    _option_key: str

    def _labels_mapping(self) -> tuple[list[str], dict[str, str]]:
        return _calendar_select_options(self.hass)

    @property
    def options(self) -> list[str]:
        labels, _mapping = self._labels_mapping()
        return labels

    @property
    def current_option(self) -> str | None:
        labels, mapping = self._labels_mapping()
        selected_entity_id = self.runtime.runtime_state.get(self._option_key)
        if not isinstance(selected_entity_id, str):
            return UNSET_OPTION
        for label, entity_id in mapping.items():
            if entity_id == selected_entity_id:
                return label
        return UNSET_OPTION if UNSET_OPTION in labels else None

    async def async_select_option(self, option: str) -> None:
        labels, mapping = self._labels_mapping()
        if option not in labels:
            raise ValueError(f"Invalid option: {option}")

        if option == UNSET_OPTION:
            self.runtime.runtime_state[self._option_key] = None
        else:
            self.runtime.runtime_state[self._option_key] = mapping[option]

        await _persist_options(self)
        self.async_write_ha_state()


class ShoppingCalendarTargetSelect(_CalendarTargetSelectBase):
    """Select target calendar for mirrored shopping completions."""

    _attr_name = "Shopping Calendar Target"
    _attr_unique_id = "hass_flatmate_shopping_calendar_target"
    _attr_icon = "mdi:calendar-check"
    _option_key = CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID


class CleaningCalendarTargetSelect(_CalendarTargetSelectBase):
    """Select target calendar for mirrored cleaning completions."""

    _attr_name = "Cleaning Calendar Target"
    _attr_unique_id = "hass_flatmate_cleaning_calendar_target"
    _attr_icon = "mdi:calendar-star"
    _option_key = CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)
    async_add_entities(
        [
            NotificationTestTargetSelect(entry, runtime),
            ShoppingCalendarTargetSelect(entry, runtime),
            CleaningCalendarTargetSelect(entry, runtime),
        ]
    )
