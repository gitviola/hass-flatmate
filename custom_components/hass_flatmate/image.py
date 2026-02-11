"""Image platform for hass_flatmate."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import HassFlatmateCoordinatorEntity, get_runtime


class ShoppingDistributionImage(HassFlatmateCoordinatorEntity, ImageEntity):
    """SVG image for shopping fairness distribution."""

    _attr_name = "Shopping Distribution 90d"
    _attr_unique_id = "hass_flatmate_shopping_distribution_90d"
    _attr_content_type = "image/svg+xml"

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, runtime) -> None:
        HassFlatmateCoordinatorEntity.__init__(self, config_entry, runtime)
        ImageEntity.__init__(self, hass)
        self._svg_version: str | None = ""
        self._image_bytes: bytes = b""
        self._last_updated: datetime | None = None

    @property
    def image_last_updated(self) -> datetime | None:
        return self._last_updated

    async def async_image(self) -> bytes | None:
        stats = self.coordinator.data.get("shopping_stats", {})
        version = stats.get("svg_render_version")

        if version != self._svg_version:
            svg = await self.runtime.api.get_buy_stats_svg(window_days=90)
            self._image_bytes = svg.encode("utf-8")
            self._svg_version = version
            self._last_updated = self.coordinator.last_update_success_time

        return self._image_bytes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)
    async_add_entities([ShoppingDistributionImage(hass, entry, runtime)])
