"""Text platform for hass_flatmate."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CLEANING_NOTIFICATION_LINK,
    CONF_NOTIFY_SHOPPING_ITEM_ADDED,
    CONF_NOTIFICATION_TEST_MODE,
    CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID,
    CONF_SHOPPING_NOTIFICATION_LINK,
    CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID,
    CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID,
    DEFAULT_CLEANING_NOTIFICATION_LINK,
    DEFAULT_NOTIFICATION_TEST_MODE,
    DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED,
    DEFAULT_SHOPPING_NOTIFICATION_LINK,
)
from .entity import HassFlatmateCoordinatorEntity, get_runtime


async def _persist_options(entity: HassFlatmateCoordinatorEntity) -> None:
    options = {
        **entity.config_entry.options,
        CONF_NOTIFICATION_TEST_MODE: bool(
            entity.runtime.runtime_state.get(CONF_NOTIFICATION_TEST_MODE, DEFAULT_NOTIFICATION_TEST_MODE)
        ),
        CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID: entity.runtime.runtime_state.get(
            CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID
        ),
        CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID: entity.runtime.runtime_state.get(
            CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID
        ),
        CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID: entity.runtime.runtime_state.get(
            CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID
        ),
        CONF_NOTIFY_SHOPPING_ITEM_ADDED: bool(
            entity.runtime.runtime_state.get(
                CONF_NOTIFY_SHOPPING_ITEM_ADDED,
                DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED,
            )
        ),
        CONF_SHOPPING_NOTIFICATION_LINK: entity.runtime.runtime_state.get(
            CONF_SHOPPING_NOTIFICATION_LINK,
            DEFAULT_SHOPPING_NOTIFICATION_LINK,
        ),
        CONF_CLEANING_NOTIFICATION_LINK: entity.runtime.runtime_state.get(
            CONF_CLEANING_NOTIFICATION_LINK,
            DEFAULT_CLEANING_NOTIFICATION_LINK,
        ),
    }
    entity.hass.config_entries.async_update_entry(entity.config_entry, options=options)


class _NotificationLinkTextBase(HassFlatmateCoordinatorEntity, TextEntity):
    _option_key: str
    _default_value: str

    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 255

    @property
    def native_value(self) -> str:
        value = self.runtime.runtime_state.get(self._option_key, self._default_value)
        if not isinstance(value, str):
            return self._default_value
        return value

    async def async_set_value(self, value: str) -> None:
        self.runtime.runtime_state[self._option_key] = str(value or "").strip()
        await _persist_options(self)
        self.async_write_ha_state()


class ShoppingNotificationLinkText(_NotificationLinkTextBase):
    """Configurable deep link/path used for shopping notifications."""

    _attr_name = "Shopping Notification Link"
    _attr_unique_id = "hass_flatmate_shopping_notification_link"
    _attr_icon = "mdi:link-variant"
    _option_key = CONF_SHOPPING_NOTIFICATION_LINK
    _default_value = DEFAULT_SHOPPING_NOTIFICATION_LINK


class CleaningNotificationLinkText(_NotificationLinkTextBase):
    """Configurable deep link/path used for cleaning notifications."""

    _attr_name = "Cleaning Notification Link"
    _attr_unique_id = "hass_flatmate_cleaning_notification_link"
    _attr_icon = "mdi:link-variant-plus"
    _option_key = CONF_CLEANING_NOTIFICATION_LINK
    _default_value = DEFAULT_CLEANING_NOTIFICATION_LINK


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)
    async_add_entities(
        [
            ShoppingNotificationLinkText(entry, runtime),
            CleaningNotificationLinkText(entry, runtime),
        ]
    )
