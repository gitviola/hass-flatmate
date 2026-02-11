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
        # Keep stable, integration-prefixed entity ids for first registration.
        unique_id = getattr(self, "_attr_unique_id", None)
        if isinstance(unique_id, str) and unique_id:
            object_id = unique_id if unique_id.startswith(f"{DOMAIN}_") else f"{DOMAIN}_{unique_id}"
            # Set both explicit object_id and suggested object_id so entity ids are
            # stable and integration-prefixed even on platforms that ignore one hint.
            self._attr_object_id = object_id
            self._attr_suggested_object_id = object_id

    @property
    def runtime(self) -> HassFlatmateRuntime:
        return self._runtime

    @property
    def config_entry(self) -> ConfigEntry:
        return self._config_entry


def get_runtime(config_entry: ConfigEntry, hass) -> HassFlatmateRuntime:
    return hass.data[DOMAIN].entries[config_entry.entry_id]
