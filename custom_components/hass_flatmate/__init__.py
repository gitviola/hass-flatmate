"""Home Assistant integration for hass-flatmate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import CONF_API_TOKEN, CONF_TYPE, CONF_URL, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .api import HassFlatmateApiClient, HassFlatmateApiError
from .const import (
    ACTIVITY_CURSOR_KEY,
    CALENDAR_CURSOR_CLEANING_KEY,
    CALENDAR_CURSOR_SHOPPING_KEY,
    CONF_BASE_URL,
    CONF_CLEANING_NOTIFICATION_LINK,
    CONF_CLEANING_TARGET_CALENDAR_ENTITY_ID,
    CONF_NOTIFY_SHOPPING_ITEM_ADDED,
    CONF_NOTIFICATION_TEST_MODE,
    CONF_NOTIFICATION_TEST_TARGET_MEMBER_ID,
    CONF_SCAN_INTERVAL,
    CONF_SHOPPING_NOTIFICATION_LINK,
    CONF_SHOPPING_TARGET_CALENDAR_ENTITY_ID,
    DEFAULT_CLEANING_NOTIFICATION_LINK,
    DEFAULT_NOTIFICATION_TEST_MODE,
    DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED,
    DEFAULT_SHOPPING_NOTIFICATION_LINK,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FRONTEND_SHOPPING_CARD_FILENAME,
    FRONTEND_SHOPPING_COMPACT_CARD_FILENAME,
    FRONTEND_CLEANING_CARD_FILENAME,
    FRONTEND_DISTRIBUTION_CARD_FILENAME,
    FRONTEND_CLEANING_CARD_RESOURCE_TYPE,
    FRONTEND_CLEANING_CARD_RESOURCE_URL,
    FRONTEND_DISTRIBUTION_CARD_RESOURCE_TYPE,
    FRONTEND_DISTRIBUTION_CARD_RESOURCE_URL,
    FRONTEND_SHOPPING_CARD_RESOURCE_TYPE,
    FRONTEND_SHOPPING_CARD_RESOURCE_URL,
    FRONTEND_SHOPPING_COMPACT_CARD_RESOURCE_TYPE,
    FRONTEND_SHOPPING_COMPACT_CARD_RESOURCE_URL,
    FRONTEND_STATIC_PATH,
    NOTIFICATION_DEDUPE_KEY,
    PLATFORMS,
    SERVICE_ADD_FAVORITE_ITEM,
    SERVICE_ADD_SHOPPING_ITEM,
    SERVICE_ATTR_CANCEL,
    SERVICE_ATTR_CLEANER_MEMBER_ID,
    SERVICE_ATTR_COMPLETED_BY_MEMBER_ID,
    SERVICE_ATTR_FAVORITE_ID,
    SERVICE_ATTR_ITEM_ID,
    SERVICE_ATTR_CLEANING_HISTORY_ROWS,
    SERVICE_ATTR_CLEANING_OVERRIDE_ROWS,
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
    SERVICE_IMPORT_MANUAL_DATA,
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
RESOURCE_ID_KEY = "id"


def _integration_version() -> str:
    manifest_path = Path(__file__).parent / "manifest.json"
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "dev"

    version = str(manifest_data.get("version", "")).strip()
    return version or "dev"


def _file_content_hash(file_path: Path) -> str:
    try:
        return hashlib.sha256(file_path.read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


def _resource_url_path(url: str) -> str:
    return urlsplit(url).path


def _resource_url_with_version(url: str, version: str) -> str:
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["v"] = version
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(params),
            parts.fragment,
        )
    )


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


def _resolve_member_notify_services(
    hass: HomeAssistant,
    runtime: HassFlatmateRuntime,
    member_id: int | None,
) -> list[str]:
    """Resolve all mobile_app notify services for a member via person -> device_trackers."""
    if member_id is None:
        return []
    members_by_id = _runtime_members_by_id(runtime)
    member = members_by_id.get(member_id)
    if member is None:
        return []
    ha_user_id = member.get("ha_user_id")
    if not ha_user_id:
        return []
    person_state = None
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == ha_user_id:
            person_state = state
            break
    if person_state is None:
        return []
    device_trackers = person_state.attributes.get("device_trackers", [])
    available = hass.services.async_services().get("notify", {})
    services: list[str] = []
    for tracker_id in device_trackers:
        if not isinstance(tracker_id, str) or not tracker_id.startswith("device_tracker."):
            continue
        service_name = tracker_id.replace("device_tracker.", "mobile_app_", 1)
        if service_name in available:
            services.append(f"notify.{service_name}")
    return services


def _normalize_notification_link(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    link = value.strip()
    if not link:
        return None
    if (
        link.startswith("/")
        or link.startswith("http://")
        or link.startswith("https://")
        or link.startswith("homeassistant://")
    ):
        return link
    return f"/{link.lstrip('/')}"


def _runtime_notification_link(runtime: HassFlatmateRuntime, category: str | None) -> str | None:
    if category == "shopping":
        return _normalize_notification_link(
            runtime.runtime_state.get(CONF_SHOPPING_NOTIFICATION_LINK, DEFAULT_SHOPPING_NOTIFICATION_LINK)
        )
    if category == "cleaning":
        return _normalize_notification_link(
            runtime.runtime_state.get(CONF_CLEANING_NOTIFICATION_LINK, DEFAULT_CLEANING_NOTIFICATION_LINK)
        )
    return None


def _notification_data_payload(*, category: str | None, link: str | None) -> dict[str, Any]:
    data: dict[str, Any] = {}

    if category == "shopping":
        data["tag"] = "hass_flatmate_shopping"
        data["group"] = "hass_flatmate_shopping"
    elif category == "cleaning":
        data["tag"] = "hass_flatmate_cleaning"
        data["group"] = "hass_flatmate_cleaning"

    if link:
        data["url"] = link  # iOS companion app.
        data["clickAction"] = link  # Android companion app.
        data["actions"] = [
            {
                "action": "URI",
                "title": "Open",
                "uri": link,
            }
        ]

    return data


def _coerce_week_start(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None
    normalized = value.strip().split("T", maxsplit=1)[0]
    if not normalized:
        return None
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        return None


def _build_cleaning_dispatch_record(
    item: dict[str, Any],
    *,
    notify_service: str | None,
    status: str,
    reason: str | None = None,
) -> dict[str, Any] | None:
    week_start = _coerce_week_start(item.get("week_start"))
    if week_start is None:
        return None

    member_id = _coerce_member_id(item.get("member_id"))
    return {
        "week_start": week_start,
        "member_id": member_id,
        "notify_service": notify_service,
        "title": item.get("title"),
        "message": item.get("message"),
        "notification_kind": item.get("notification_kind"),
        "notification_slot": item.get("notification_slot"),
        "source_action": item.get("source_action"),
        "status": status,
        "reason": reason,
        "dispatched_at": dt_util.utcnow().isoformat(),
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


def _set_activity_cursor_from_events(runtime: HassFlatmateRuntime) -> None:
    activity_cursor = _coerce_activity_id(runtime.runtime_state.get(ACTIVITY_CURSOR_KEY))
    for row in runtime.coordinator.data.get("activity", []):
        if not isinstance(row, dict):
            continue
        row_id = _coerce_activity_id(row.get("id"))
        if row_id is None:
            continue
        activity_cursor = row_id if activity_cursor is None else max(activity_cursor, row_id)
    runtime.runtime_state[ACTIVITY_CURSOR_KEY] = activity_cursor


def _build_activity_event_data(
    row: dict[str, Any],
    *,
    row_id: int,
    members_by_id: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    payload = row.get("payload_json", {})
    if not isinstance(payload, dict):
        payload = {}

    actor_member_id = _coerce_member_id(row.get("actor_member_id"))
    actor_name: str | None = None
    if actor_member_id is not None:
        actor_name = members_by_id.get(actor_member_id, {}).get("display_name")
        if not isinstance(actor_name, str):
            actor_name = None

    summary, _description = _event_summary_and_description(row)
    return {
        "activity_id": row_id,
        "domain": row.get("domain"),
        "action": row.get("action"),
        "created_at": row.get("created_at"),
        "actor_member_id": actor_member_id,
        "actor_name": actor_name,
        "actor_user_id_raw": row.get("actor_user_id_raw"),
        "payload": payload,
        "summary": summary,
    }


def _build_shopping_added_notifications(
    runtime: HassFlatmateRuntime,
    row: dict[str, Any],
    *,
    members_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not bool(
        runtime.runtime_state.get(
            CONF_NOTIFY_SHOPPING_ITEM_ADDED,
            DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED,
        )
    ):
        return []

    payload = row.get("payload_json", {})
    if not isinstance(payload, dict):
        payload = {}
    item_name = str(payload.get("name", "")).strip()
    if not item_name:
        item_name = "an item"

    actor_member_id = _coerce_member_id(row.get("actor_member_id"))
    actor_name = None
    if actor_member_id is not None:
        actor_name = members_by_id.get(actor_member_id, {}).get("display_name")
    if not isinstance(actor_name, str) or not actor_name.strip():
        actor_name = "Someone"

    notifications: list[dict[str, Any]] = []
    for member_id, member in members_by_id.items():
        if actor_member_id is not None and member_id == actor_member_id:
            continue
        if not bool(member.get("active", True)):
            continue
        notify_service = member.get("notify_service")
        if not isinstance(notify_service, str) or not notify_service:
            continue
        notifications.append(
            {
                "member_id": member_id,
                "notify_service": notify_service,
                "title": "Shopping List Updated",
                "message": f"{actor_name} added {item_name} to the shopping list.",
                "category": "shopping",
            }
        )
    return notifications


async def _emit_new_activity_events(hass: HomeAssistant, runtime: HassFlatmateRuntime) -> None:
    rows = runtime.coordinator.data.get("activity", [])
    if not isinstance(rows, list):
        return

    last_cursor = _coerce_activity_id(runtime.runtime_state.get(ACTIVITY_CURSOR_KEY))
    members_by_id = _runtime_members_by_id(runtime)
    candidates: list[tuple[int, dict[str, Any]]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = _coerce_activity_id(row.get("id"))
        if row_id is None:
            continue
        if last_cursor is not None and row_id <= last_cursor:
            continue
        candidates.append((row_id, row))

    if not candidates:
        return

    candidates.sort(key=lambda item: item[0])
    next_cursor = last_cursor

    for row_id, row in candidates:
        action = str(row.get("action", "")).strip().lower()
        event_data = _build_activity_event_data(row, row_id=row_id, members_by_id=members_by_id)
        hass.bus.async_fire("hass_flatmate_activity", event_data)
        if action:
            hass.bus.async_fire(f"hass_flatmate_activity_{action}", event_data)

        if action == "shopping_item_added":
            shopping_notifications = _build_shopping_added_notifications(
                runtime,
                row,
                members_by_id=members_by_id,
            )
            if shopping_notifications:
                try:
                    await _dispatch_notifications(
                        hass,
                        runtime,
                        shopping_notifications,
                        default_category="shopping",
                    )
                except Exception as err:  # pragma: no cover - defensive
                    _LOGGER.warning("Failed to dispatch shopping-added notifications: %s", err)

        next_cursor = row_id if next_cursor is None else max(next_cursor, row_id)

    runtime.runtime_state[ACTIVITY_CURSOR_KEY] = next_cursor


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
    await _emit_new_activity_events(hass, runtime)
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

    payload: list[dict[str, Any]] = []
    for user in users:
        if not user.is_active or user.system_generated:
            continue

        person_entity_id = person_by_user_id.get(user.id)
        notify_service = None
        if person_entity_id:
            person_state = hass.states.get(person_entity_id)
            if person_state:
                for tracker_id in (person_state.attributes.get("device_trackers") or []):
                    if isinstance(tracker_id, str) and tracker_id.startswith("device_tracker."):
                        svc = tracker_id.replace("device_tracker.", "mobile_app_", 1)
                        if svc in notify_services:
                            notify_service = f"notify.{svc}"
                            break

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
    *,
    default_category: str | None = None,
) -> None:
    test_mode_enabled = bool(runtime.runtime_state.get(CONF_NOTIFICATION_TEST_MODE, DEFAULT_NOTIFICATION_TEST_MODE))
    test_target = _runtime_notification_test_target(runtime) if test_mode_enabled else None
    dispatch_records: list[dict[str, Any]] = []
    members_by_id = _runtime_members_by_id(runtime)

    if test_mode_enabled and test_target is None:
        _LOGGER.warning(
            "Notification test mode is enabled but no valid target member is configured; "
            "suppressing %s notifications",
            len(notifications),
        )
        for item in notifications:
            category = item.get("category") if isinstance(item.get("category"), str) else default_category
            category = str(category) if category else None
            if category != "cleaning":
                continue
            record = _build_cleaning_dispatch_record(
                item,
                notify_service=item.get("notify_service"),
                status="suppressed",
                reason="notification_test_mode_enabled_without_target",
            )
            if record is not None:
                dispatch_records.append(record)
        if dispatch_records:
            try:
                await runtime.api.record_cleaning_notification_dispatch(records=dispatch_records)
            except HassFlatmateApiError as exc:
                _LOGGER.debug("Failed to persist cleaning notification dispatch log: %s", exc)
        return

    for item in notifications:
        title = item.get("title", "Weekly Cleaning Shift")
        message = item.get("message", "")
        category = item.get("category") if isinstance(item.get("category"), str) else default_category
        category = str(category) if category else None

        member_id = _coerce_member_id(item.get("member_id"))

        if test_mode_enabled and test_target is not None:
            target_services = [test_target["notify_service"]]
            title = f"[TEST] {title}"
            if member_id is not None:
                original_name = members_by_id.get(member_id, {}).get("display_name")
                if original_name:
                    message = f"[Intended for {original_name}] {message}"
                else:
                    message = f"[Intended for member {member_id}] {message}"
        else:
            target_services = _resolve_member_notify_services(hass, runtime, member_id)
            if not target_services:
                fallback = item.get("notify_service")
                target_services = [fallback] if fallback else []

        if not target_services:
            if category == "cleaning":
                record = _build_cleaning_dispatch_record(
                    item,
                    notify_service=None,
                    status="skipped",
                    reason="missing_notify_service",
                )
                if record is not None:
                    dispatch_records.append(record)
            continue

        for notify_service in target_services:
            if not notify_service:
                continue

            if "." not in notify_service:
                _LOGGER.warning("Invalid notify service format: %s", notify_service)
                if category == "cleaning":
                    record = _build_cleaning_dispatch_record(
                        item,
                        notify_service=notify_service,
                        status="skipped",
                        reason="invalid_notify_service_format",
                    )
                    if record is not None:
                        dispatch_records.append(record)
                continue

            domain, service = notify_service.split(".", 1)
            if domain != "notify":
                _LOGGER.warning("Unsupported notify domain: %s", notify_service)
                if category == "cleaning":
                    record = _build_cleaning_dispatch_record(
                        item,
                        notify_service=notify_service,
                        status="skipped",
                        reason="unsupported_notify_domain",
                    )
                    if record is not None:
                        dispatch_records.append(record)
                continue

            link = _runtime_notification_link(runtime, category)
            if "deeplink" in item:
                link = _normalize_notification_link(item.get("deeplink"))
            svc_payload = {
                "title": title,
                "message": message,
            }
            data_payload = _notification_data_payload(category=category, link=link)
            if data_payload:
                svc_payload["data"] = data_payload

            status_value = "sent"
            reason: str | None = None
            try:
                await hass.services.async_call(
                    domain,
                    service,
                    svc_payload,
                    blocking=False,
                )
                if test_mode_enabled and test_target is not None:
                    status_value = "test_redirected"
            except Exception as err:  # pragma: no cover - depends on runtime service availability
                status_value = "failed"
                reason = str(err)
                _LOGGER.warning("Failed to dispatch notification via %s: %s", notify_service, err)

            if category == "cleaning":
                record = _build_cleaning_dispatch_record(
                    item,
                    notify_service=notify_service,
                    status=status_value,
                    reason=reason,
                )
                if record is not None:
                    dispatch_records.append(record)

    if dispatch_records:
        try:
            await runtime.api.record_cleaning_notification_dispatch(records=dispatch_records)
        except HassFlatmateApiError as exc:
            _LOGGER.debug("Failed to persist cleaning notification dispatch log: %s", exc)


async def _sync_members_from_ha(runtime: HassFlatmateRuntime, hass: HomeAssistant) -> None:
    payload = await _build_member_sync_payload(hass)
    response = await runtime.api.sync_members(payload)
    if not isinstance(response, dict):
        return
    notifications = response.get("notifications", [])
    if isinstance(notifications, list) and notifications:
        await _dispatch_notifications(
            hass,
            runtime,
            notifications,
            default_category="cleaning",
        )


async def _handle_due_notifications(hass: HomeAssistant, runtime: HassFlatmateRuntime) -> None:
    now = dt_util.now().replace(second=0, microsecond=0)
    dedupe_key = now.isoformat()
    if runtime.runtime_state.get(NOTIFICATION_DEDUPE_KEY) == dedupe_key:
        return

    runtime.runtime_state[NOTIFICATION_DEDUPE_KEY] = dedupe_key

    response = await runtime.api.get_due_notifications(at=now)
    notifications = response.get("notifications", [])
    if notifications:
        await _dispatch_notifications(
            hass,
            runtime,
            notifications,
            default_category="cleaning",
        )


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
        response = await runtime.api.mark_cleaning_done(
            week_start=week_start,
            actor_user_id=call.context.user_id,
            completed_by_member_id=call.data.get(SERVICE_ATTR_COMPLETED_BY_MEMBER_ID),
        )
        await _dispatch_notifications(
            hass,
            runtime,
            response.get("notifications", []),
            default_category="cleaning",
        )
        _schedule_refresh_and_process_activity(hass, runtime)

    async def mark_cleaning_undone(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        await runtime.api.mark_cleaning_undone(
            week_start=week_start,
            actor_user_id=call.context.user_id,
        )
        _schedule_refresh_and_process_activity(hass, runtime)

    async def mark_cleaning_takeover_done(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        week_start = date.fromisoformat(call.data[SERVICE_ATTR_WEEK_START])
        response = await runtime.api.mark_cleaning_takeover_done(
            week_start=week_start,
            original_assignee_member_id=call.data[SERVICE_ATTR_ORIGINAL_ASSIGNEE_MEMBER_ID],
            cleaner_member_id=call.data[SERVICE_ATTR_CLEANER_MEMBER_ID],
            actor_user_id=call.context.user_id,
        )
        await _dispatch_notifications(
            hass,
            runtime,
            response.get("notifications", []),
            default_category="cleaning",
        )
        _schedule_refresh_and_process_activity(hass, runtime)

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
        await _dispatch_notifications(
            hass,
            runtime,
            response.get("notifications", []),
            default_category="cleaning",
        )
        _schedule_refresh_and_process_activity(hass, runtime)

    async def sync_members(_call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        await _sync_members_from_ha(runtime, hass)
        _schedule_refresh_and_process_activity(hass, runtime)

    async def import_manual_data(call: ServiceCall) -> None:
        runtime = _get_primary_runtime(hass)
        try:
            response = await runtime.api.import_manual_data(
                rotation_rows=call.data.get(SERVICE_ATTR_ROTATION_ROWS),
                cleaning_history_rows=call.data.get(SERVICE_ATTR_CLEANING_HISTORY_ROWS),
                shopping_history_rows=call.data.get(SERVICE_ATTR_SHOPPING_HISTORY_ROWS),
                cleaning_override_rows=call.data.get(SERVICE_ATTR_CLEANING_OVERRIDE_ROWS),
                actor_user_id=call.context.user_id,
            )
        except HassFlatmateApiError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await _dispatch_notifications(
            hass,
            runtime,
            response.get("notifications", []),
        )
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
        schema=vol.Schema(
            {
                vol.Required(SERVICE_ATTR_WEEK_START): cv.string,
                vol.Optional(SERVICE_ATTR_COMPLETED_BY_MEMBER_ID): cv.positive_int,
            }
        ),
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
        SERVICE_IMPORT_MANUAL_DATA,
        import_manual_data,
        schema=vol.Schema(
            {
                vol.Optional(SERVICE_ATTR_ROTATION_ROWS, default=""): cv.string,
                vol.Optional(SERVICE_ATTR_CLEANING_HISTORY_ROWS, default=""): cv.string,
                vol.Optional(SERVICE_ATTR_SHOPPING_HISTORY_ROWS, default=""): cv.string,
                vol.Optional(SERVICE_ATTR_CLEANING_OVERRIDE_ROWS, default=""): cv.string,
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
        (FRONTEND_SHOPPING_COMPACT_CARD_FILENAME, FRONTEND_SHOPPING_COMPACT_CARD_RESOURCE_URL),
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
        static_paths.append(StaticPathConfig(resource_url, str(static_file), True))

    if not static_paths:
        return

    await hass.http.async_register_static_paths(static_paths)
    data.frontend_registered = True


async def _register_lovelace_card_resource(hass: HomeAssistant) -> None:
    """Auto-register hass-flatmate card resources for Lovelace storage mode."""
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

    resource_targets_base = [
        {
            CONF_URL: FRONTEND_SHOPPING_CARD_RESOURCE_URL,
            CONF_TYPE: FRONTEND_SHOPPING_CARD_RESOURCE_TYPE,
            CONF_RESOURCE_TYPE_WS: FRONTEND_SHOPPING_CARD_RESOURCE_TYPE,
        },
        {
            CONF_URL: FRONTEND_SHOPPING_COMPACT_CARD_RESOURCE_URL,
            CONF_TYPE: FRONTEND_SHOPPING_COMPACT_CARD_RESOURCE_TYPE,
            CONF_RESOURCE_TYPE_WS: FRONTEND_SHOPPING_COMPACT_CARD_RESOURCE_TYPE,
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
    integration_version = _integration_version()
    resource_targets = []
    for target in resource_targets_base:
        file_path = Path(__file__).parent / "frontend" / _resource_url_path(target[CONF_URL]).rsplit("/", 1)[-1]
        file_hash = _file_content_hash(file_path)
        version_tag = f"{integration_version}-{file_hash}"
        resource_targets.append({
            CONF_URL: _resource_url_with_version(target[CONF_URL], version_tag),
            CONF_TYPE: target[CONF_TYPE],
            CONF_RESOURCE_TYPE_WS: target[CONF_RESOURCE_TYPE_WS],
            "resource_path": _resource_url_path(target[CONF_URL]),
        })

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
    existing_items = list(resources.async_items() or [])
    delete_resource_item = getattr(resources, "async_delete_item", None)
    update_resource_item = getattr(resources, "async_update_item", None)

    def _resource_item_type(item: dict[str, Any]) -> str:
        item_type = item.get(CONF_TYPE) or item.get(CONF_RESOURCE_TYPE_WS)
        return str(item_type) if item_type else ""

    async def _refresh_existing_items() -> None:
        nonlocal existing_items
        await resources.async_get_info()
        existing_items = list(resources.async_items() or [])

    async def _replace_resource_item(existing_item: dict[str, Any], target: dict[str, Any]) -> bool:
        item_id = existing_item.get(RESOURCE_ID_KEY)
        if item_id is None:
            return False

        payload = {
            CONF_RESOURCE_TYPE_WS: target[CONF_RESOURCE_TYPE_WS],
            CONF_URL: target[CONF_URL],
        }

        if callable(update_resource_item):
            try:
                await update_resource_item(item_id, payload)
                return True
            except Exception as err:  # pragma: no cover - defensive for HA API edge cases
                _LOGGER.debug(
                    "Failed to update Lovelace resource id=%s to %s: %s",
                    item_id,
                    target[CONF_URL],
                    err,
                )

        if not callable(delete_resource_item):
            return False

        try:
            await delete_resource_item(item_id)
        except Exception as err:  # pragma: no cover - defensive for HA API edge cases
            _LOGGER.debug(
                "Failed to delete stale Lovelace resource id=%s before recreate: %s",
                item_id,
                err,
            )
            return False

        try:
            await resources.async_create_item(payload)
            return True
        except Exception as err:  # pragma: no cover - defensive for HA API edge cases
            _LOGGER.warning(
                "Failed to recreate Lovelace resource %s after deleting stale id=%s: %s",
                target[CONF_URL],
                item_id,
                err,
            )
            return False

    for target in resource_targets:
        target_url = str(target[CONF_URL])
        target_type = str(target[CONF_TYPE])
        target_path = str(target["resource_path"])

        exact_match = next(
            (
                item
                for item in existing_items
                if str(item.get(CONF_URL) or "") == target_url
                and _resource_item_type(item) == target_type
            ),
            None,
        )
        if exact_match is not None:
            continue

        stale_matches = [
            item
            for item in existing_items
            if _resource_item_type(item) == target_type
            and _resource_url_path(str(item.get(CONF_URL) or "")) == target_path
        ]

        if stale_matches:
            replaced = await _replace_resource_item(stale_matches[0], target)
            if replaced:
                _LOGGER.info(
                    "Updated Lovelace resource to cache-busted URL: %s",
                    target_url,
                )
                if callable(delete_resource_item):
                    for duplicate in stale_matches[1:]:
                        duplicate_id = duplicate.get(RESOURCE_ID_KEY)
                        if duplicate_id is None:
                            continue
                        try:
                            await delete_resource_item(duplicate_id)
                        except Exception as err:  # pragma: no cover
                            _LOGGER.debug(
                                "Failed to remove duplicate stale Lovelace resource id=%s: %s",
                                duplicate_id,
                                err,
                            )
                await _refresh_existing_items()
            else:
                _LOGGER.warning(
                    "Found stale Lovelace resource for %s but could not update it automatically",
                    target_path,
                )
            continue

        try:
            await resources.async_create_item(
                {
                    CONF_RESOURCE_TYPE_WS: target[CONF_RESOURCE_TYPE_WS],
                    CONF_URL: target_url,
                }
            )
            _LOGGER.info(
                "Auto-registered Lovelace resource: %s",
                target_url,
            )
            await _refresh_existing_items()
        except Exception as err:  # pragma: no cover - defensive for HA API edge cases
            _LOGGER.warning(
                "Failed to auto-register Lovelace resource %s: %s",
                target_url,
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
        if not isinstance(unique_id, str) or not unique_id:
            continue

        expected_object_id = unique_id if unique_id.startswith(f"{DOMAIN}_") else f"{DOMAIN}_{unique_id}"
        # Legacy installs used object ids derived from entity names, i.e. without
        # domain prefix (shopping_open_count instead of hass_flatmate_shopping_open_count).
        legacy_object_id = (
            unique_id[len(f"{DOMAIN}_") :]
            if unique_id.startswith(f"{DOMAIN}_")
            else unique_id
        )
        current_object_id = entity_entry.entity_id.split(".", 1)[1]
        # Respect explicit user custom entity ids unless they still match the
        # old non-prefixed defaults (including numeric collision variants).
        is_legacy_default = current_object_id == legacy_object_id
        is_legacy_collision = current_object_id.startswith(f"{legacy_object_id}_")
        if not (is_legacy_default or is_legacy_collision):
            continue

        new_entity_id = f"{entity_entry.entity_id.split('.', 1)[0]}.{expected_object_id}"
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
    runtime.runtime_state[CONF_NOTIFY_SHOPPING_ITEM_ADDED] = bool(
        entry.options.get(
            CONF_NOTIFY_SHOPPING_ITEM_ADDED,
            DEFAULT_NOTIFY_SHOPPING_ITEM_ADDED,
        )
    )
    runtime.runtime_state[CONF_SHOPPING_NOTIFICATION_LINK] = str(
        entry.options.get(
            CONF_SHOPPING_NOTIFICATION_LINK,
            DEFAULT_SHOPPING_NOTIFICATION_LINK,
        )
        or ""
    )
    runtime.runtime_state[CONF_CLEANING_NOTIFICATION_LINK] = str(
        entry.options.get(
            CONF_CLEANING_NOTIFICATION_LINK,
            DEFAULT_CLEANING_NOTIFICATION_LINK,
        )
        or ""
    )

    try:
        await _sync_members_from_ha(runtime, hass)
        await coordinator.async_request_refresh()
    except (HassFlatmateApiError, Exception) as exc:
        raise ConfigEntryNotReady(
            f"Backend not ready during setup: {exc}"
        ) from exc
    _set_calendar_cursors_from_events(runtime)
    _set_activity_cursor_from_events(runtime)

    async def _time_listener(now) -> None:
        del now
        await _handle_due_notifications(hass, runtime)

    runtime.unsub_time_listener = async_track_time_change(hass, _time_listener, second=0)

    data = _get_domain_data(hass)
    data.entries[entry.entry_id] = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _migrate_legacy_entity_ids(hass, entry)
    await _register_lovelace_card_resource(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = _get_domain_data(hass)
    runtime = data.entries.pop(entry.entry_id)
    if runtime.unsub_time_listener is not None:
        runtime.unsub_time_listener()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
