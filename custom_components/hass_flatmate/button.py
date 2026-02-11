"""Button platform for hass_flatmate."""

from __future__ import annotations

from datetime import date

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
        week_start = date.fromisoformat(str(week_start_raw))

        await self.runtime.api.mark_cleaning_done(
            week_start=week_start,
            actor_user_id=None,
        )
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)
    async_add_entities([MarkCleaningDoneButton(entry, runtime)])
