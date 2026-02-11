"""Switch platform for hass_flatmate."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CLEANING_NOTIFICATION_LINK,
    CONF_NOTIFY_SHOPPING_ITEM_ADDED,
    CONF_NOTIFICATION_TEST_MODE,
    CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID,
    CONF_SHOPPING_NOTIFICATION_LINK,
    DEFAULT_NOTIFICATION_TEST_MODE,
    DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED,
)
from .entity import HassFlatmateCoordinatorEntity, get_runtime


def _coerce_member_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _valid_target_member_ids(runtime) -> list[int]:
    ids: list[int] = []
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
        ids.append(member_id)
    return ids


async def _persist_options(entity: HassFlatmateCoordinatorEntity) -> None:
    options = {
        **entity.config_entry.options,
        CONF_NOTIFICATION_TEST_MODE: bool(
            entity.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_MODE, DEFAULT_NOTIFICATION_TEST_MODE)
        ),
        CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID: _coerce_member_id(
            entity.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID)
        ),
        CONF_NOTIFY_SHOPPING_ITEM_ADDED: bool(
            entity.runtime.runtime_state.get(
                CONF_NOTIFY_SHOPPING_ITEM_ADDED, DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED
            )
        ),
        CONF_SHOPPING_NOTIFICATION_LINK: entity.runtime.runtime_state.get(
            CONF_SHOPPING_NOTIFICATION_LINK
        ),
        CONF_CLEANING_NOTIFICATION_LINK: entity.runtime.runtime_state.get(
            CONF_CLEANING_NOTIFICATION_LINK
        ),
    }
    entity.hass.config_entries.async_update_entry(entity.config_entry, options=options)


class NotificationTestModeSwitch(HassFlatmateCoordinatorEntity, SwitchEntity):
    """Toggle notification test mode for safe rollout validation."""

    _attr_name = "Notification Test Mode"
    _attr_unique_id = "hass_flatmate_notification_test_mode"
    _attr_icon = "mdi:test-tube"

    @property
    def is_on(self) -> bool:
        return bool(self.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_MODE, DEFAULT_NOTIFICATION_TEST_MODE))

    async def async_turn_on(self, **kwargs: Any) -> None:
        del kwargs
        self.runtime.runtime_state[CONF_NOTIFICATION_TEST_MODE] = True

        current_target = _coerce_member_id(
            self.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID)
        )
        valid_ids = _valid_target_member_ids(self.runtime)
        if current_target not in valid_ids and valid_ids:
            self.runtime.runtime_state[CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID] = valid_ids[0]

        await _persist_options(self)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        del kwargs
        self.runtime.runtime_state[CONF_NOTIFICATION_TEST_MODE] = False
        await _persist_options(self)
        self.async_write_ha_state()


class ShoppingAddedNotificationSwitch(HassFlatmateCoordinatorEntity, SwitchEntity):
    """Toggle built-in shopping-added push notifications."""

    _attr_name = "Notify Shopping Item Added"
    _attr_unique_id = "hass_flatmate_notify_shopping_item_added"
    _attr_icon = "mdi:cart-arrow-down"

    @property
    def is_on(self) -> bool:
        return bool(
            self.runtime.runtime_state.get(
                CONF_NOTIFY_SHOPPING_ITEM_ADDED,
                DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED,
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        del kwargs
        self.runtime.runtime_state[CONF_NOTIFY_SHOPPING_ITEM_ADDED] = True
        await _persist_options(self)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        del kwargs
        self.runtime.runtime_state[CONF_NOTIFY_SHOPPING_ITEM_ADDED] = False
        await _persist_options(self)
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)
    async_add_entities(
        [
            NotificationTestModeSwitch(entry, runtime),
            ShoppingAddedNotificationSwitch(entry, runtime),
        ]
    )
