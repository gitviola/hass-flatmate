"""Home Assistant integration for hass-flatmate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import HassFlatmateApiClient
from .const import (
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    NOTIFICATION_DEDUPE_KEY,
    PLATFORMS,
    SERVICE_ADD_FAVORITE_ITEM,
    SERVICE_ADD_SHOPPING_ITEM,
    SERVICE_ATTR_CANCEL,
    SERVICE_ATTR_CLEANER_MEMBER_ID,
    SERVICE_ATTR_FAVORITE_ID,
    SERVICE_ATTR_ITEM_ID,
    SERVICE_ATTR_MEMBER_A_ID,
    SERVICE_ATTR_MEMBER_B_ID,
    SERVICE_ATTR_NAME,
    SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID,
    SERVICE_ATTR_WEEK_START,
    SERVICE_COMPLETE_SHOPPING_ITEM,
    SERVICE_DELETE_FAVORITE_ITEM,
    SERVICE_DELETE_SHOPPING_ITEM,
    SERVICE_MARK_CLEANING_DONE,
    SERVICE_MARK_CLEANING_TAKEOVER_DONE,
    SERVICE_SWAP_CLEANING_WEEK,
    SERVICE_SYNC_MEMBERS,
)
from .coordinator import HassFlatmateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class HassFlatmateRuntime:
    """Runtime object per config entry."""

    api: HassFlatmateApiClient
    coordinator: HassFlatmateCoordinator
    unsub_time_listener: Any | None = None
    runtime_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class HassFlatmateData:
    """Integration-wide runtime storage."""

    entries: dict[str, HassFlatmateRuntime] = field(default_factory=dict)
    services_registered: bool = False


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _get_domain_data(hass: HomeAssistant) -> HassFlatmateData:
    return hass.data.setdefault(DOMAIN, HassFlatmateData())


def _get_primary_runtime(hass: HomeAssistant) -> HassFlatmateRuntime:
    data = _get_domain_data(hass)
    if not data.entries:
        raise HomeAssistantError("No active hass_flatmate entry configured")
    first_key = next(iter(data.entries))
    return data.entries[first_key]


async def _build_member_sync_payload(hass: HomeAssistant) -> list[dict[str, Any]]:
    users = await hass.auth.async_get_users()
    person_by_user_id: dict[str, str] = {}
    for state in hass.states.async_all("person"):
        user_id = state.attributes.get("user_id")
        if user_id:
            person_by_user_id[user_id] = state.entity_id

    notify_services = hass.services.async_services().get("notify", {})
    notify_service_names = list(notify_services.keys())

    payload: list[dict[str, Any]] = []
    for user in users:
        if not user.is_active or user.system_generated:
            continue

        norm_name = _normalize_name(user.name)
        notify_service = next(
            (f"notify.{service}" for service in notify_service_names if norm_name and norm_name in service),
            None,
        )

        payload.append(
            {
                "display_name": user.name,
                "ha_user_id": user.id,
                "ha_person_entity_id": person_by_user_id.get(user.id),
                "notify_service": notify_service,
                "active": True,
            }
        )

    return payload


async def _dispatch_notifications(hass: HomeAssistant, notifications: list[dict[str, Any]]) -> None:
    for item in notifications:
        notify_service = item.get("notify_service")
        if not notify_service:
            continue

        if "." not in notify_service:
            _LOGGER.warning("Invalid notify service format: %s", notify_service)
            continue

        domain, service = notify_service.split(".", 1)
        if domain != "notify":
            _LOGGER.warning("Unsupported notify domain: %s", notify_service)
            continue

        await hass.services.async_call(
            domain,
            service,
            {
                "title": item.get("title", "Weekly Cleaning Shift"),
                "message": item.get("message", ""),
            },
            blocking=False,
        )


async def _sync_members_from_ha(runtime: HassFlatmateRuntime, hass: HomeAssistant) -> None:
    payload = await _build_member_sync_payload(hass)
    await runtime.api.sync_members(payload)


async def _handle_due_notifications(hass: HomeAssistant, runtime: HassFlatmateRuntime) -> None:
    now = dt_util.now().replace(second=0, microsecond=0)
    dedupe_key = now.isoformat()
    if runtime.runtime_state.get(NOTIFICATION_DEDUPE_KEY) == dedupe_key:
        return

    runtime.runtime_state[NOTIFICATION_DEDUPE_KEY] = dedupe_key

    response = await runtime.api.get_due_notifications(at=now)
    notifications = response.get("notifications", [])
    if notifications:
        await _dispatch_notifications(hass, notifications)


async def _register_services(hass: HomeAssistant) -> None:
    data = _get_domain_data(hass)
    if data.services_registered:
        return

    async def add_shopping_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.add_shopping_item(
            name=call.data[SERVICE_ATTR_NAME],
            actor_user_id=call.context.user_id,
        )
        await runtime.coordinator.async_request_refresh()

    async def complete_shopping_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.complete_shopping_item(
            item_id=call.data[SERVICE_ATTR_ITEM_ID],
            actor_user_id=call.context.user_id,
        )
        await runtime.coordinator.async_request_refresh()

    async def delete_shopping_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.delete_shopping_item(
            item_id=call.data[SERVICE_ATTR_ITEM_ID],
            actor_user_id=call.context.user_id,
        )
        await runtime.coordinator.async_request_refresh()

    async def add_favorite_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.add_favorite_item(
            name=call.data[SERVICE_ATTR_NAME],
            actor_user_id=call.context.user_id,
        )
        await runtime.coordinator.async_request_refresh()

    async def delete_favorite_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.delete_favorite_item(
            favorite_id=call.data[SERVICE_ATTR_FAVORITE_ID],
            actor_user_id=call.context.user_id,
        )
        await runtime.coordinator.async_request_refresh()

    async def mark_cleaning_done(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        await runtime.api.mark_cleaning_done(
            week_start=week_start,
            actor_user_id=call.context.user_id,
        )
        await runtime.coordinator.async_request_refresh()

    async def mark_cleaning_takeover_done(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        response = await runtime.api.mark_cleaning_takeover_done(
            week_start=week_start,
            original_assignee_member_id=call.data[SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID],
            cleaner_member_id=call.data[SERVICE_ATTR_CLEANER_MEMBER_ID],
            actor_user_id=call.context.user_id,
        )
        await _dispatch_notifications(hass, response.get("notifications", []))
        await runtime.coordinator.async_request_refresh()

    async def swap_cleaning_week(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        response = await runtime.api.swap_cleaning_week(
            week_start=week_start,
            member_a_id=call.data[SERVICE_ATTR_MEMBER_A_ID],
            member_b_id=call.data[SERVICE_ATTR_MEMBER_B_ID],
            actor_user_id=call.context.user_id,
            cancel=call.data.get(SERVICE_ATTR_CANCEL, False),
        )
        await _dispatch_notifications(hass, response.get("notifications", []))
        await runtime.coordinator.async_request_refresh()

    async def sync_members(_call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await _sync_members_from_ha(runtime, hass)
        await runtime.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_SHOPPING_ITEM,
        add_shopping_item,
        schema=vol.Schema({vol.Required(SERVICE_ATTR_NAME): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_COMPLETE_SHOPPING_ITEM,
        complete_shopping_item,
        schema=vol.Schema({vol.Required(SERVICE_ATTR_ITEM_ID): cv.positive_int}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SHOPPING_ITEM,
        delete_shopping_item,
        schema=vol.Schema({vol.Required(SERVICE_ATTR_ITEM_ID): cv.positive_int}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_FAVORITE_ITEM,
        add_favorite_item,
        schema=vol.Schema({vol.Required(SERVICE_ATTR_NAME): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FAVORITE_ITEM,
        delete_favorite_item,
        schema=vol.Schema({vol.Required(SERVICE_ATTR_FAVORITE_ID): cv.positive_int}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MARK_CLEANING_DONE,
        mark_cleaning_done,
        schema=vol.Schema({vol.Required(SERVICE_ATTR_WEEK_START): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MARK_CLEANING_TAKEOVER_DONE,
        mark_cleaning_takeover_done,
        schema=vol.Schema(
            {
                vol.Required(SERVICE_ATTR_WEEK_START): cv.string,
                vol.Required(SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID): cv.positive_int,
                vol.Required(SERVICE_ATTR_CLEANER_MEMBER_ID): cv.positive_int,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SWAP_CLEANING_WEEK,
        swap_cleaning_week,
        schema=vol.Schema(
            {
                vol.Required(SERVICE_ATTR_WEEK_START): cv.string,
                vol.Required(SERVICE_ATTR_MEMBER_A_ID): cv.positive_int,
                vol.Required(SERVICE_ATTR_MEMBER_B_ID): cv.positive_int,
                vol.Optional(SERVICE_ATTR_CANCEL, default=False): cv.boolean,
            }
        ),
    )
    hass.services.async_register(DOMAIN, SERVICE_SYNC_MEMBERS, sync_members)

    data.services_registered = True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    del config
    _get_domain_data(hass)
    await _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = HassFlatmateApiClient(
        session,
        base_url=entry.data[CONF_BASE_URL],
        api_token=entry.data[CONF_API_TOKEN],
    )

    coordinator = HassFlatmateCoordinator(
        hass,
        api,
        update_interval_seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    runtime = HassFlatmateRuntime(api=api, coordinator=coordinator)
    await _sync_members_from_ha(runtime, hass)
    await coordinator.async_request_refresh()

    async def _time_listener(now) -> None:
        del now
        await _handle_due_notifications(hass, runtime)

    runtime.unsub_time_listener = async_track_time_change(hass, _time_listener, second=0)

    data = _get_domain_data(hass)
    data.entries[entry.entry_id] = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = _get_domain_data(hass)
    runtime = data.entries.pop(entry.entry_id)
    if runtime.unsub_time_listener is not None:
        runtime.unsub_time_listener()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
