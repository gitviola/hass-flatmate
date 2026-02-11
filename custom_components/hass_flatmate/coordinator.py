"""DataUpdateCoordinator for hass_flatmate integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HassFlatmateApiClient, HassFlatmateApiError
from .const import COORDINATOR_NAME


class HassFlatmateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches all dashboard-facing data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: HassFlatmateApiClient,
        *,
        update_interval_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=COORDINATOR_NAME,
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            (
                members,
                shopping_items,
                shopping_recents,
                shopping_favorites,
                shopping_stats,
                cleaning_current,
                cleaning_schedule,
                activity,
            ) = await asyncio.gather(
                self.api.get_members(),
                self.api.get_shopping_items(),
                self.api.get_recents(limit=20),
                self.api.get_favorites(),
                self.api.get_buy_stats(window_days=90),
                self.api.get_cleaning_current(),
                self.api.get_cleaning_schedule(weeks_ahead=12, include_previous_weeks=1),
                self.api.get_activity(limit=200),
            )
        except HassFlatmateApiError as exc:
            raise UpdateFailed(str(exc)) from exc

        return {
            "members": members,
            "shopping_items": shopping_items,
            "shopping_recents": shopping_recents.get("recents", []),
            "shopping_favorites": shopping_favorites.get("favorites", []),
            "shopping_stats": shopping_stats,
            "cleaning_current": cleaning_current,
            "cleaning_schedule": cleaning_schedule,
            "activity": activity,
        }
