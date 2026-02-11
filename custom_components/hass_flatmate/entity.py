"""Shared entity helpers for hass_flatmate."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import HassFlatmateRuntime
from .const import DOMAIN


class HassFlatmateCoordinatorEntity(CoordinatorEntity):
    """Base coordinator entity for hass_flatmate."""

    def __init__(self, config_entry: ConfigEntry, runtime: HassFlatmateRuntime) -> None:
        super().__init__(runtime.coordinator)
        self._config_entry = config_entry
        self._runtime = runtime
        self._attr_has_entity_name = True

    @property
    def runtime(self) -> HassFlatmateRuntime:
        return self._runtime


def get_runtime(config_entry: ConfigEntry, hass) -> HassFlatmateRuntime:
    return hass.data[DOMAIN].entries[config_entry.entry_id]
