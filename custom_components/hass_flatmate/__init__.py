"""Home Assistant integration for hass-flatmate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import logging
from pathlib import Path
import re
from typing import Any

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN, CONF_TYPE, CONF_URL, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import HassFlatmateApiClient
from .const import (
    CALENDAR_CURSOR_CLEANING_KEY,
    CALENDAR_CURSOR_SHOPPING_KEY,
    CONF_BASE_URL,
    CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID,
    CONF_NOTIFICATION_TEST_MODE,
    CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID,
    CONF_SCAN_INTERVAL,
    CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID,
    DEFAULT_NOTIFICATION_TEST_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FRONTEND_SHOPPING_CARD_FILENAME,
    FRONTEND_CLEANING_CARD_FILENAME,
    FRONTEND_DISTRIBUTION_CARD_FILENAME,
    FRONTEND_CLEANING_CARD_RESOURCE_TYPE,
    FRONTEND_CLEANING_CARD_RESOURCE_URL,
    FRONTEND_DISTRIBUTION_CARD_RESOURCE_TYPE,
    FRONTEND_DISTRIBUTION_CARD_RESOURCE_URL,
    FRONTEND_SHOPPING_CARD_RESOURCE_TYPE,
    FRONTEND_SHOPPING_CARD_RESOURCE_URL,
    FRONTEND_STATIC_PATH,
    NOTIFICATION_DEDUPE_KEY,
    PLATFORMS,
    SERVICE_ADD_FAVORITE_ITEM,
    SERVICE_ADD_SHOPPING_ITEM,
    SERVICE_ATTR_CANCEL,
    SERVICE_ATTR_CLEANER_MEMBER_ID,
    SERVICE_ATTR_FAVORITE_ID,
    SERVICE_ATTR_ITEM_ID,
    SERVICE_ATTR_CLEANING_HISTORY_ROWS,
    SERVICE_ATTR_MEMBER_A_ID,
    SERVICE_ATTR_MEMBER_B_ID,
    SERVICE_ATTR_NAME,
    SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID,
    SERVICE_ATTR_ROTATION_ROWS,
    SERVICE_ATTR_SHOPPING_HISTORY_ROWS,
    SERVICE_ATTR_WEEK_START,
    SERVICE_COMPLETE_SHOPPING_ITEM,
    SERVICE_DELETE_FAVORITE_ITEM,
    SERVICE_DELETE_SHOPPING_ITEM,
    SERVICE_IMPORT_FLATASTIC_DATA,
    SERVICE_MARK_CLEANING_DONE,
    SERVICE_MARK_CLEANING_UNDONE,
    SERVICE_MARK_CLEANING_TAKEOVER_DONE,
    SERVICE_SWAP_CLEANING_WEEK,
    SERVICE_SYNC_MEMBERS,
)
from .coordinator import HassFlatmateCoordinator
from .discovery import async_discover_service_base_url

_LOGGER = logging.getLogger(__name__)
REFRESH_TASK_KEY = "_refresh_activity_task"
REFRESH_PENDING_KEY = "_refresh_activity_pending"


def _is_loopback_base_url(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("http://127.0.0.1") or normalized.startswith("http://localhost")


def _coerce_member_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    frontend_registered: bool = False


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _runtime_members_by_id(runtime: HassFlatmateRuntime) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for member in runtime.coordinator.data.get("members", []):
        if not isinstance(member, dict):
            continue
        member_id = _coerce_member_id(member.get("id"))
        if member_id is None:
            continue
        result[member_id] = member
    return result


def _runtime_notification_test_target(runtime: HassFlatmateRuntime) -> dict[str, Any] | None:
    target_member_id = _coerce_member_id(runtime.runtime_state.get(CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID))
    if target_member_id is None:
        return None

    member = _runtime_members_by_id(runtime).get(target_member_id)
    if member is None:
        return None

    notify_service = member.get("notify_service")
    if not isinstance(notify_service, str) or not notify_service:
        return None

    return {
        "member_id": target_member_id,
        "display_name": member.get("display_name", str(target_member_id)),
        "notify_service": notify_service,
    }


def _coerce_activity_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _event_category(action: str) -> str | None:
    if action == "shopping_item_completed":
        return "shopping"
    if action in {"cleaning_done", "cleaning_takeover_done"}:
        return "cleaning"
    return None


def _event_summary_and_description(row: dict[str, Any]) -> tuple[str | None, str]:
    action = str(row.get("action", ""))
    payload = row.get("payload_json", {})
    if not isinstance(payload, dict):
        payload = {}

    if action == "shopping_item_completed":
        item_name = str(payload.get("name", "item"))
        return f"Shopping completed: {item_name}", action
    if action == "cleaning_done":
        return "Cleaning completed", action
    if action == "cleaning_takeover_done":
        return "Cleaning completed (takeover)", action
    return None, action


def _event_start_datetime(row: dict[str, Any]) -> Any | None:
    created_raw = row.get("created_at")
    if created_raw is None:
        return None

    parsed = dt_util.parse_datetime(str(created_raw))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = dt_util.as_utc(parsed)
    return dt_util.as_local(parsed)


def _runtime_selected_calendar_for_category(runtime: HassFlatmateRuntime, category: str) -> str | None:
    key = (
        CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID
        if category == "shopping"
        else CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID
    )
    selected = runtime.runtime_state.get(key)
    if isinstance(selected, str) and selected.startswith("calendar."):
        return selected
    return None


def _set_calendar_cursors_from_events(runtime: HassFlatmateRuntime) -> None:
    shopping_cursor = _coerce_activity_id(runtime.runtime_state.get(CALENDAR_CURSOR_SHOPPING_KEY))
    cleaning_cursor = _coerce_activity_id(runtime.runtime_state.get(CALENDAR_CURSOR_CLEANING_KEY))

    for row in runtime.coordinator.data.get("activity", []):
        if not isinstance(row, dict):
            continue
        row_id = _coerce_activity_id(row.get("id"))
        if row_id is None:
            continue
        category = _event_category(str(row.get("action", "")))
        if category == "shopping":
            shopping_cursor = row_id if shopping_cursor is None else max(shopping_cursor, row_id)
        elif category == "cleaning":
            cleaning_cursor = row_id if cleaning_cursor is None else max(cleaning_cursor, row_id)

    runtime.runtime_state[CALENDAR_CURSOR_SHOPPING_KEY] = shopping_cursor
    runtime.runtime_state[CALENDAR_CURSOR_CLEANING_KEY] = cleaning_cursor


async def _sync_activity_to_selected_calendars(hass: HomeAssistant, runtime: HassFlatmateRuntime) -> None:
    rows = runtime.coordinator.data.get("activity", [])
    if not isinstance(rows, list):
        return

    last_shopping = _coerce_activity_id(runtime.runtime_state.get(CALENDAR_CURSOR_SHOPPING_KEY))
    last_cleaning = _coerce_activity_id(runtime.runtime_state.get(CALENDAR_CURSOR_CLEANING_KEY))
    next_shopping = last_shopping
    next_cleaning = last_cleaning

    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = _coerce_activity_id(row.get("id"))
        if row_id is None:
            continue
        category = _event_category(str(row.get("action", "")))
        if category is None:
            continue
        if category == "shopping" and last_shopping is not None and row_id <= last_shopping:
            continue
        if category == "cleaning" and last_cleaning is not None and row_id <= last_cleaning:
            continue
        candidates.append((row_id, category, row))

    candidates.sort(key=lambda item: item[0])

    for row_id, category, row in candidates:
        target_calendar = _runtime_selected_calendar_for_category(runtime, category)
        summary, description = _event_summary_and_description(row)
        start_dt = _event_start_datetime(row)
        end_dt = start_dt + timedelta(minutes=15) if start_dt is not None else None

        if target_calendar and summary and start_dt and end_dt:
            try:
                await hass.services.async_call(
                    "calendar",
                    "create_event",
                    {
                        "entity_id": target_calendar,
                        "summary": summary,
                        "description": description,
                        "start_date_time": start_dt,
                        "end_date_time": end_dt,
                    },
                    blocking=True,
                )
            except Exception as err:  # pragma: no cover - depends on calendar provider features
                _LOGGER.warning(
                    "Unable to mirror %s activity event %s to %s: %s",
                    category,
                    row_id,
                    target_calendar,
                    err,
                )

        if category == "shopping":
            next_shopping = row_id if next_shopping is None else max(next_shopping, row_id)
        elif category == "cleaning":
            next_cleaning = row_id if next_cleaning is None else max(next_cleaning, row_id)

    runtime.runtime_state[CALENDAR_CURSOR_SHOPPING_KEY] = next_shopping
    runtime.runtime_state[CALENDAR_CURSOR_CLEANING_KEY] = next_cleaning


async def _refresh_and_process_activity(hass: HomeAssistant, runtime: HassFlatmateRuntime) -> None:
    await runtime.coordinator.async_request_refresh()
    await _sync_activity_to_selected_calendars(hass, runtime)


def _schedule_refresh_and_process_activity(hass: HomeAssistant, runtime: HassFlatmateRuntime) -> None:
    existing_task = runtime.runtime_state.get(REFRESH_TASK_KEY)
    if existing_task is not None and not existing_task.done():
        runtime.runtime_state[REFRESH_PENDING_KEY] = True
        return

    runtime.runtime_state[REFRESH_PENDING_KEY] = True

    async def _runner() -> None:
        try:
            while runtime.runtime_state.pop(REFRESH_PENDING_KEY, False):
                await _refresh_and_process_activity(hass, runtime)
        except Exception:  # pragma: no cover - defensive logging
            _LOGGER.exception("Background refresh/activity sync failed")
        finally:
            runtime.runtime_state.pop(REFRESH_TASK_KEY, None)

    runtime.runtime_state[REFRESH_TASK_KEY] = hass.async_create_task(_runner())


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


async def _dispatch_notifications(
    hass: HomeAssistant,
    runtime: HassFlatmateRuntime,
    notifications: list[dict[str, Any]],
) -> None:
    test_mode_enabled = bool(runtime.runtime_state.get(CONF_NOTIFICATION_TEST_MODE, DEFAULT_NOTIFICATION_TEST_MODE))
    test_target = _runtime_notification_test_target(runtime) if test_mode_enabled else None
    if test_mode_enabled and test_target is None:
        _LOGGER.warning(
            "Notification test mode is enabled but no valid target member is configured; "
            "suppressing %s notifications",
            len(notifications),
        )
        return

    members_by_id = _runtime_members_by_id(runtime)

    for item in notifications:
        notify_service = item.get("notify_service")
        title = item.get("title", "Weekly Cleaning Shift")
        message = item.get("message", "")

        if test_mode_enabled and test_target is not None:
            notify_service = test_target["notify_service"]
            title = f"[TEST] {title}"

            original_member_id = _coerce_member_id(item.get("member_id"))
            if original_member_id is not None:
                original_name = members_by_id.get(original_member_id, {}).get("display_name")
                if original_name:
                    message = f"[Intended for {original_name}] {message}"
                else:
                    message = f"[Intended for member {original_member_id}] {message}"

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
                "title": title,
                "message": message,
            },
            blocking=False,
        )


async def _sync_members_from_ha(runtime: HassFlatmateRuntime, hass: HomeAssistant) -> None:
    payload = await _build_member_sync_payload(hass)
    response = await runtime.api.sync_members(payload)
    if not isinstance(response, dict):
        return
    notifications = response.get("notifications", [])
    if isinstance(notifications, list) and notifications:
        await _dispatch_notifications(hass, runtime, notifications)


async def _handle_due_notifications(hass: HomeAssistant, runtime: HassFlatmateRuntime) -> None:
    now = dt_util.now().replace(second=0, microsecond=0)
    dedupe_key = now.isoformat()
    if runtime.runtime_state.get(NOTIFICATION_DEDUPE_KEY) == dedupe_key:
        return

    runtime.runtime_state[NOTIFICATION_DEDUPE_KEY] = dedupe_key

    response = await runtime.api.get_due_notifications(at=now)
    notifications = response.get("notifications", [])
    if notifications:
        await _dispatch_notifications(hass, runtime, notifications)


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
        _schedule_refresh_and_process_activity(hass, runtime)

    async def complete_shopping_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.complete_shopping_item(
            item_id=call.data[SERVICE_ATTR_ITEM_ID],
            actor_user_id=call.context.user_id,
        )
        _schedule_refresh_and_process_activity(hass, runtime)

    async def delete_shopping_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.delete_shopping_item(
            item_id=call.data[SERVICE_ATTR_ITEM_ID],
            actor_user_id=call.context.user_id,
        )
        _schedule_refresh_and_process_activity(hass, runtime)

    async def add_favorite_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.add_favorite_item(
            name=call.data[SERVICE_ATTR_NAME],
            actor_user_id=call.context.user_id,
        )
        _schedule_refresh_and_process_activity(hass, runtime)

    async def delete_favorite_item(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await runtime.api.delete_favorite_item(
            favorite_id=call.data[SERVICE_ATTR_FAVORITE_ID],
            actor_user_id=call.context.user_id,
        )
        _schedule_refresh_and_process_activity(hass, runtime)

    async def mark_cleaning_done(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        await runtime.api.mark_cleaning_done(
            week_start=week_start,
            actor_user_id=call.context.user_id,
        )
        await _refresh_and_process_activity(hass, runtime)

    async def mark_cleaning_undone(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        await runtime.api.mark_cleaning_undone(
            week_start=week_start,
            actor_user_id=call.context.user_id,
        )
        await _refresh_and_process_activity(hass, runtime)

    async def mark_cleaning_takeover_done(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        response = await runtime.api.mark_cleaning_takeover_done(
            week_start=week_start,
            original_assignee_member_id=call.data[SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID],
            cleaner_member_id=call.data[SERVICE_ATTR_CLEANER_MEMBER_ID],
            actor_user_id=call.context.user_id,
        )
        await _dispatch_notifications(hass, runtime, response.get("notifications", []))
        await _refresh_and_process_activity(hass, runtime)

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
        await _dispatch_notifications(hass, runtime, response.get("notifications", []))
        await _refresh_and_process_activity(hass, runtime)

    async def sync_members(_call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await _sync_members_from_ha(runtime, hass)
        _schedule_refresh_and_process_activity(hass, runtime)

    async def import_flatastic_data(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        response = await runtime.api.import_flatastic_data(
            rotation_rows=call.data.get(SERVICE_ATTR_ROTATION_ROWS),
            cleaning_history_rows=call.data.get(SERVICE_ATTR_CLEANING_HISTORY_ROWS),
            shopping_history_rows=call.data.get(SERVICE_ATTR_SHOPPING_HISTORY_ROWS),
            actor_user_id=call.context.user_id,
        )
        await _dispatch_notifications(hass, runtime, response.get("notifications", []))
        await _refresh_and_process_activity(hass, runtime)

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
        SERVICE_MARK_CLEANING_UNDONE,
        mark_cleaning_undone,
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
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_FLATASTIC_DATA,
        import_flatastic_data,
        schema=vol.Schema(
            {
                vol.Optional(SERVICE_ATTR_ROTATION_ROWS, default=""): cv.string,
                vol.Optional(SERVICE_ATTR_CLEANING_HISTORY_ROWS, default=""): cv.string,
                vol.Optional(SERVICE_ATTR_SHOPPING_HISTORY_ROWS, default=""): cv.string,
            }
        ),
    )

    data.services_registered = True


async def _register_frontend_static_assets(hass: HomeAssistant) -> None:
    data = _get_domain_data(hass)
    if data.frontend_registered:
        return

    targets = [
        (FRONTEND_SHOPPING_CARD_FILENAME, FRONTEND_SHOPPING_CARD_RESOURCE_URL),
        (FRONTEND_CLEANING_CARD_FILENAME, FRONTEND_CLEANING_CARD_RESOURCE_URL),
        (FRONTEND_DISTRIBUTION_CARD_FILENAME, FRONTEND_DISTRIBUTION_CARD_RESOURCE_URL),
    ]
    static_paths: list[StaticPathConfig] = []
    for filename, resource_url in targets:
        static_file = Path(__file__).parent / "frontend" / filename
        if not static_file.exists():
            _LOGGER.warning(
                "Frontend asset not found, skipping static registration: %s",
                static_file,
            )
            continue
        static_paths.append(StaticPathConfig(resource_url, str(static_file), False))

    if not static_paths:
        return

    await hass.http.async_register_static_paths(static_paths)
    data.frontend_registered = True


async def _register_lovelace_card_resource(hass: HomeAssistant) -> None:
    """Auto-register the shopping card resource for Lovelace storage mode."""
    try:
        from homeassistant.components.lovelace.const import (
            CONF_RESOURCE_TYPE_WS,
            LOVELACE_DATA,
            MODE_STORAGE,
        )
    except ImportError:
        return

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        return

    resource_targets = [
        {
            CONF_URL: FRONTEND_SHOPPING_CARD_RESOURCE_URL,
            CONF_TYPE: FRONTEND_SHOPPING_CARD_RESOURCE_TYPE,
            CONF_RESOURCE_TYPE_WS: FRONTEND_SHOPPING_CARD_RESOURCE_TYPE,
        },
        {
            CONF_URL: FRONTEND_CLEANING_CARD_RESOURCE_URL,
            CONF_TYPE: FRONTEND_CLEANING_CARD_RESOURCE_TYPE,
            CONF_RESOURCE_TYPE_WS: FRONTEND_CLEANING_CARD_RESOURCE_TYPE,
        },
        {
            CONF_URL: FRONTEND_DISTRIBUTION_CARD_RESOURCE_URL,
            CONF_TYPE: FRONTEND_DISTRIBUTION_CARD_RESOURCE_TYPE,
            CONF_RESOURCE_TYPE_WS: FRONTEND_DISTRIBUTION_CARD_RESOURCE_TYPE,
        },
    ]

    if lovelace_data.resource_mode != MODE_STORAGE:
        resource_urls = ", ".join(target[CONF_URL] for target in resource_targets)
        _LOGGER.debug(
            "Lovelace resource mode is '%s'; add resources manually if needed: %s",
            lovelace_data.resource_mode,
            resource_urls,
        )
        return

    resources = lovelace_data.resources
    await resources.async_get_info()
    existing = {
        (item.get(CONF_URL), item.get(CONF_TYPE))
        for item in (resources.async_items() or [])
    }

    for target in resource_targets:
        key = (target[CONF_URL], target[CONF_TYPE])
        if key in existing:
            continue

        try:
            await resources.async_create_item(
                {
                    CONF_RESOURCE_TYPE_WS: target[CONF_RESOURCE_TYPE_WS],
                    CONF_URL: target[CONF_URL],
                }
            )
            _LOGGER.info(
                "Auto-registered Lovelace resource: %s",
                target[CONF_URL],
            )
        except Exception as err:  # pragma: no cover - defensive for HA API edge cases
            _LOGGER.warning(
                "Failed to auto-register Lovelace resource %s: %s",
                target[CONF_URL],
                err,
            )


async def _migrate_legacy_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate old unprefixed hass_flatmate entity ids to prefixed object ids."""
    registry = er.async_get(hass)
    migrated = 0

    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity_entry.platform != DOMAIN:
            continue

        unique_id = entity_entry.unique_id
        if not isinstance(unique_id, str) or not unique_id.startswith(f"{DOMAIN}_"):
            continue

        # Legacy installs used object ids derived from entity names, i.e. without
        # domain prefix (shopping_open_count instead of hass_flatmate_shopping_open_count).
        legacy_object_id = unique_id[len(f"{DOMAIN}_") :]
        current_object_id = entity_entry.entity_id.split(".", 1)[1]
        if current_object_id != legacy_object_id:
            continue

        new_entity_id = f"{entity_entry.entity_id.split('.', 1)[0]}.{unique_id}"
        if new_entity_id == entity_entry.entity_id:
            continue

        try:
            registry.async_update_entity(entity_entry.entity_id, new_entity_id=new_entity_id)
            migrated += 1
        except ValueError:
            _LOGGER.warning(
                "Could not migrate entity id %s to %s (target already exists)",
                entity_entry.entity_id,
                new_entity_id,
            )

    if migrated:
        _LOGGER.info("Migrated %s hass_flatmate entity id(s) to prefixed object ids", migrated)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    del config
    _get_domain_data(hass)
    await _register_frontend_static_assets(hass)
    await _register_lovelace_card_resource(hass)

    @callback
    def _register_resource_on_started(_event: Event) -> None:
        hass.async_create_task(_register_lovelace_card_resource(hass))

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_resource_on_started)
    await _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_base_url = entry.data[CONF_BASE_URL]
    resolved_base_url = entry_base_url
    if _is_loopback_base_url(entry_base_url):
        discovered_base_url = await async_discover_service_base_url(hass)
        if discovered_base_url:
            resolved_base_url = discovered_base_url
            if discovered_base_url != entry_base_url:
                hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_BASE_URL: discovered_base_url},
                )
                _LOGGER.info(
                    "Updated hass_flatmate base_url from loopback to discovered app URL: %s",
                    discovered_base_url,
                )

    session = async_get_clientsession(hass)
    api = HassFlatmateApiClient(
        session,
        base_url=resolved_base_url,
        api_token=entry.data[CONF_API_TOKEN],
    )

    coordinator = HassFlatmateCoordinator(
        hass,
        api,
        update_interval_seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    runtime = HassFlatmateRuntime(api=api, coordinator=coordinator)
    runtime.runtime_state[CONF_NOTIFICATION_TEST_MODE] = bool(
        entry.options.get(CONF_NOTIFICATION_TEST_MODE, DEFAULT_NOTIFICATION_TEST_MODE)
    )
    runtime.runtime_state[CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID] = _coerce_member_id(
        entry.options.get(CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID)
    )
    runtime.runtime_state[CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID] = entry.options.get(
        CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID
    )
    runtime.runtime_state[CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID] = entry.options.get(
        CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID
    )

    await _sync_members_from_ha(runtime, hass)
    await coordinator.async_request_refresh()
    _set_calendar_cursors_from_events(runtime)

    async def _time_listener(now) -> None:
        del now
        await _handle_due_notifications(hass, runtime)

    runtime.unsub_time_listener = async_track_time_change(hass, _time_listener, second=0)

    data = _get_domain_data(hass)
    data.entries[entry.entry_id] = runtime

    await _migrate_legacy_entity_ids(hass, entry)
    await _register_lovelace_card_resource(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = _get_domain_data(hass)
    runtime = data.entries.pop(entry.entry_id)
    if runtime.unsub_time_listener is not None:
        runtime.unsub_time_listener()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
