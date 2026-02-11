"""Button platform for hass_flatmate."""

from __future__ import annotations

from datetime import date

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SERVICE_ATTR_WEEK_START, SERVICE_MARK_CLEANING_DONE
from .entity import HassFlatmateCoordinatorEntity, get_runtime


class MarkCleaningDoneButton(HassFlatmateCoordinatorEntity, ButtonEntity):
    """One-click button to mark current week cleaning done."""

    _attr_name = "Mark Cleaning Done"
    _attr_unique_id = "hass_flatmate_mark_cleaning_done"
    _attr_icon = "mdi:check-bold"

    async def async_press(self) -> None:
        current = self.coordinator.data.get("cleaning_current", {})
        week_start_raw = current.get("week_start")
        if week_start_raw is None:
            return
        week_start = date.fromisoformat(str(week_start_raw)).isoformat()

        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_MARK_CLEANING_DONE,
            {SERVICE_ATTR_WEEK_START: week_start},
            blocking=True,
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)
    async_add_entities([MarkCleaningDoneButton(entry, runtime)])
