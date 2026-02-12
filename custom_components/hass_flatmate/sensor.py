"""Sensor platform for hass_flatmate."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SERVICE_ADD_FAVORITE_ITEM,
    SERVICE_ADD_SHOPPING_ITEM,
    SERVICE_MARK_CLEANING_DONE,
    SERVICE_MARK_CLEANING_TAKEOVER_DONE,
    SERVICE_MARK_CLEANING_UNDONE,
    SERVICE_SWAP_CLEANING_WEEK,
    SERVICE_COMPLETE_SHOPPING_ITEM,
    SERVICE_DELETE_SHOPPING_ITEM,
    SERVICE_DELETE_FAVORITE_ITEM,
)
from .entity import HassFlatmateCoordinatorEntity, get_runtime


def _member_lookup(data: Mapping[str, Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for member in data.get("members", []):
        if member.get("id") is not None:
            result[int(member["id"])] = member.get("display_name", str(member["id"]))
    return result


def _parse_datetime_local(value: Any) -> datetime | None:
    if value is None:
        return None
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = dt_util.as_utc(parsed)
    return dt_util.as_local(parsed)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_week_start_iso(value: Any) -> str | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return parsed.isoformat()


def _activity_actor_name(row: Mapping[str, Any], members: Mapping[int, str]) -> str:
    actor_id = row.get("actor_member_id")
    if actor_id is not None:
        try:
            member_name = members.get(int(actor_id))
        except (TypeError, ValueError):
            member_name = None
        if member_name:
            return member_name
    return "Someone"


def _cleaning_event_week_starts(payload: Mapping[str, Any]) -> set[str]:
    week_starts: set[str] = set()
    for key in ("week_start", "source_week_start", "compensation_week_start", "return_week_start"):
        week_start_iso = _parse_week_start_iso(payload.get(key))
        if week_start_iso:
            week_starts.add(week_start_iso)
    return week_starts


def _cleaning_history_summary(
    action: str,
    payload: Mapping[str, Any],
    members: Mapping[int, str],
    actor_name: str,
) -> str:
    if action == "cleaning_done":
        return f"{actor_name} marked this shift done"
    if action == "cleaning_undone":
        return f"{actor_name} reverted this shift to pending"
    if action == "cleaning_takeover_done":
        cleaner_id = payload.get("cleaner_member_id")
        cleaner_name = None
        if cleaner_id is not None:
            try:
                cleaner_name = members.get(int(cleaner_id))
            except (TypeError, ValueError):
                cleaner_name = None
        if cleaner_name:
            return f"{actor_name} recorded takeover by {cleaner_name}"
        return f"{actor_name} recorded a takeover completion"
    if action == "cleaning_swap_created":
        return f"{actor_name} created a shift swap"
    if action == "cleaning_swap_updated":
        return f"{actor_name} updated a shift swap"
    if action == "cleaning_swap_canceled":
        return f"{actor_name} canceled a shift swap"
    if action == "cleaning_compensation_planned":
        return f"{actor_name} planned a make-up shift"
    if action == "cleaning_override_auto_canceled_member_inactive":
        return "A planned override was canceled because a flatmate left"
    if action == "cleaning_notification_dispatch":
        status = str(payload.get("status", "")).strip().lower()
        slot = str(payload.get("notification_slot", "")).strip().lower()
        slot_label_map = {
            "monday_11": "Monday assignment",
            "sunday_18": "Sunday evening reminder",
            "sunday_21": "Sunday final reminder",
        }
        status_label_map = {
            "sent": "Sent",
            "test_redirected": "Sent (test mode)",
            "failed": "Failed",
            "skipped": "Skipped",
            "suppressed": "Suppressed",
        }
        slot_label = slot_label_map.get(slot, "notification")
        status_label = status_label_map.get(status, status.title() or "Unknown")
        return f"{slot_label}: {status_label}"
    return action.replace("_", " ")


def _build_cleaning_history_by_week(
    activity_rows: list[Any],
    *,
    members: Mapping[int, str],
) -> dict[str, list[dict[str, Any]]]:
    now_local = dt_util.now()
    cutoff = now_local - timedelta(days=7)
    history_by_week: dict[str, list[dict[str, Any]]] = {}

    for row in activity_rows:
        if not isinstance(row, Mapping):
            continue

        if str(row.get("domain", "")).strip().lower() != "cleaning":
            continue

        payload = row.get("payload_json", {})
        if not isinstance(payload, Mapping):
            payload = {}

        week_starts = _cleaning_event_week_starts(payload)
        if not week_starts:
            continue

        created_local = _parse_datetime_local(row.get("created_at"))
        if created_local is None or created_local < cutoff:
            continue

        action = str(row.get("action", "")).strip().lower()
        actor_name = _activity_actor_name(row, members)
        history_item = {
            "id": row.get("id"),
            "created_at": created_local.isoformat(),
            "summary": _cleaning_history_summary(action, payload, members, actor_name),
            "action": action,
            "actor_name": actor_name,
            "notification_slot": payload.get("notification_slot"),
            "dispatch_status": payload.get("status"),
            "reason": payload.get("reason"),
            "_sort_key": created_local.timestamp(),
        }

        for week_start in week_starts:
            history_by_week.setdefault(week_start, []).append(dict(history_item))

    for week_start, events in history_by_week.items():
        events.sort(key=lambda item: float(item.get("_sort_key", 0.0)), reverse=True)
        trimmed = events[:30]
        for item in trimmed:
            item.pop("_sort_key", None)
        history_by_week[week_start] = trimmed

    return history_by_week


def _format_slot_moment(slot_moment: datetime) -> str:
    return slot_moment.strftime("%a, %b %-d at %H:%M")


def _notification_slots_for_week(
    *,
    week_start: date,
    completed_at: datetime | None,
    week_status: str | None,
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    now_local = dt_util.now()
    slot_tz = dt_util.DEFAULT_TIME_ZONE or now_local.tzinfo or dt_util.UTC
    slot_defs = [
        ("monday_11", "Monday assignment reminder", 0, 11),
        ("sunday_18", "Sunday evening reminder", 6, 18),
        ("sunday_21", "Sunday final reminder", 6, 21),
    ]
    status_labels = {
        "sent": "Sent",
        "test_redirected": "Sent (test mode)",
        "failed": "Failed",
        "skipped": "Skipped",
        "suppressed": "Suppressed",
        "scheduled": "Scheduled",
        "not_required": "Skipped — done early",
        "no_data": "No data",
        "missing": "Missing",
    }

    latest_dispatch_by_slot: dict[str, dict[str, Any]] = {}
    for event in history:
        if str(event.get("action", "")).strip().lower() != "cleaning_notification_dispatch":
            continue
        slot = str(event.get("notification_slot", "")).strip().lower()
        if not slot or slot in latest_dispatch_by_slot:
            continue
        latest_dispatch_by_slot[slot] = event

    has_any_dispatch = bool(latest_dispatch_by_slot)

    slots: list[dict[str, Any]] = []
    for slot_id, label, day_offset, hour in slot_defs:
        slot_moment = datetime.combine(
            week_start + timedelta(days=day_offset),
            time(hour=hour, minute=0),
            tzinfo=slot_tz,
        )

        dispatch_event = latest_dispatch_by_slot.get(slot_id)
        if dispatch_event is not None:
            state = str(dispatch_event.get("dispatch_status", "")).strip().lower() or "sent"
            detail = dispatch_event.get("summary")
            slots.append(
                {
                    "slot": slot_id,
                    "label": label,
                    "state": state,
                    "state_label": status_labels.get(state, state.title()),
                    "detail": detail,
                    "last_event_at": dispatch_event.get("created_at"),
                }
            )
            continue

        if now_local < slot_moment:
            state = "scheduled"
            detail = f"Scheduled for {_format_slot_moment(slot_moment)}"
        elif slot_id.startswith("sunday_") and (
            (completed_at is not None and completed_at <= slot_moment)
            or (week_status == "done" and completed_at is None)
        ):
            state = "not_required"
            detail = "Cleaning was completed before this reminder was due"
        elif has_any_dispatch:
            state = "missing"
            detail = "Expected notification was not recorded"
        else:
            state = "no_data"
            detail = "Notification tracking was not available for this week"

        slots.append(
            {
                "slot": slot_id,
                "label": label,
                "state": state,
                "state_label": status_labels.get(state, state.title()),
                "detail": detail,
                "last_event_at": None,
            }
        )

    return slots


_TIMELINE_EVENT_ICONS: dict[str, str] = {
    "cleaning_done": "mdi:check-circle",
    "cleaning_undone": "mdi:undo-variant",
    "cleaning_takeover_done": "mdi:account-switch",
    "cleaning_swap_created": "mdi:swap-horizontal",
    "cleaning_swap_updated": "mdi:swap-horizontal",
    "cleaning_swap_canceled": "mdi:close-circle",
    "cleaning_compensation_planned": "mdi:calendar-plus",
    "cleaning_override_auto_canceled_member_inactive": "mdi:account-remove",
}

_TIMELINE_NOTIFICATION_ICONS: dict[str, str] = {
    "sent": "mdi:bell-check",
    "test_redirected": "mdi:bell-check",
    "failed": "mdi:bell-off",
    "skipped": "mdi:bell-off",
    "suppressed": "mdi:bell-off",
    "scheduled": "mdi:bell-clock",
    "not_required": "mdi:bell-minus",
    "no_data": "mdi:bell-outline",
    "missing": "mdi:bell-outline",
}


def _build_week_timeline(
    *,
    notification_slots: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    now_local = dt_util.now()
    timeline: list[dict[str, Any]] = []

    for slot in notification_slots:
        state = str(slot.get("state", "")).strip().lower()
        is_future = state == "scheduled"
        icon = _TIMELINE_NOTIFICATION_ICONS.get(state, "mdi:bell-outline")
        timestamp = slot.get("last_event_at")
        summary = str(slot.get("label", "Notification"))
        detail = slot.get("detail")
        state_label = slot.get("state_label")

        ts_val = _parse_datetime_local(timestamp) if timestamp else None
        if is_future and detail and not timestamp:
            ts_val = None

        timeline.append({
            "type": "notification",
            "timestamp": ts_val.isoformat() if ts_val else None,
            "is_future": is_future,
            "icon": icon,
            "summary": summary,
            "detail": str(detail) if detail else None,
            "state": state or None,
            "state_label": str(state_label) if state_label else None,
            "_sort_ts": ts_val.timestamp() if ts_val else 0.0,
        })

    dispatch_slots_seen = {
        str(slot.get("slot", "")).strip().lower()
        for slot in notification_slots
        if slot.get("last_event_at")
    }

    for event in history:
        action = str(event.get("action", "")).strip().lower()
        if action == "cleaning_notification_dispatch":
            notif_slot = str(event.get("notification_slot", "")).strip().lower()
            if notif_slot in dispatch_slots_seen:
                continue

        icon = _TIMELINE_EVENT_ICONS.get(action, "mdi:information")
        timestamp = event.get("created_at")
        ts_val = _parse_datetime_local(timestamp) if timestamp else None
        is_future = ts_val > now_local if ts_val else False
        summary = str(event.get("summary", action.replace("_", " ")))
        reason = event.get("reason")

        timeline.append({
            "type": "event",
            "timestamp": ts_val.isoformat() if ts_val else None,
            "is_future": is_future,
            "icon": icon,
            "summary": summary,
            "detail": str(reason) if reason else None,
            "state": None,
            "state_label": None,
            "_sort_ts": ts_val.timestamp() if ts_val else 0.0,
        })

    future_items = [e for e in timeline if e["is_future"]]
    past_items = [e for e in timeline if not e["is_future"]]
    future_items.sort(key=lambda e: e["_sort_ts"])
    past_items.sort(key=lambda e: e["_sort_ts"], reverse=True)

    result = future_items + past_items
    for entry in result:
        entry.pop("_sort_ts", None)
    return result


def _activity_summary(row: Mapping[str, Any], members: Mapping[int, str]) -> str:
    action = str(row.get("action", ""))
    payload = row.get("payload_json", {})
    if not isinstance(payload, Mapping):
        payload = {}

    actor_name = None
    actor_id = row.get("actor_member_id")
    if actor_id is not None:
        try:
            actor_name = members.get(int(actor_id))
        except (TypeError, ValueError):
            actor_name = None

    if action == "shopping_item_added":
        item_name = str(payload.get("name", "item"))
        return f"{actor_name or 'Someone'} added {item_name}"
    if action == "shopping_item_completed":
        item_name = str(payload.get("name", "item"))
        return f"{actor_name or 'Someone'} bought {item_name}"
    if action == "shopping_item_deleted":
        item_name = str(payload.get("name", "item"))
        return f"{actor_name or 'Someone'} removed {item_name}"
    if action == "cleaning_done":
        return f"{actor_name or 'Someone'} marked cleaning as done"
    if action == "cleaning_takeover_done":
        return f"{actor_name or 'Someone'} completed a cleaning takeover"
    if action == "cleaning_swap_created":
        return "A cleaning swap was created"
    if action == "cleaning_swap_canceled":
        return "A cleaning swap was canceled"
    if action == "cleaning_override_auto_canceled_member_inactive":
        return "A cleaning override was canceled because a flatmate left"
    if action in {"manual_import_applied", "flatastic_import_applied"}:
        return "Manual data import applied"
    return action.replace("_", " ")


class ShoppingOpenCountSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Shopping Open Count"
    _attr_unique_id = "hass_flatmate_shopping_open_count"
    _attr_icon = "mdi:cart-outline"

    @property
    def native_value(self) -> int:
        items = self.coordinator.data.get("shopping_items", [])
        return sum(1 for item in items if item.get("status") == "open")


class ShoppingDistributionSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Shopping Distribution 90d"
    _attr_unique_id = "hass_flatmate_shopping_distribution_90d"
    _attr_icon = "mdi:chart-bar"

    @property
    def native_value(self) -> int:
        stats = self.coordinator.data.get("shopping_stats", {})
        return int(stats.get("total_completed", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.data.get("shopping_stats", {})
        return {
            "window_days": int(stats.get("window_days", 90)),
            "total_completed": int(stats.get("total_completed", 0)),
            "unknown_excluded_count": int(stats.get("unknown_excluded_count", 0)),
            "distribution": stats.get("distribution", []),
            "svg_render_version": stats.get("svg_render_version", ""),
        }


class ShoppingDataSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Shopping Data"
    _attr_unique_id = "hass_flatmate_shopping_data"
    _attr_icon = "mdi:format-list-bulleted-square"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        items = self.coordinator.data.get("shopping_items", [])
        return sum(1 for item in items if item.get("status") == "open")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        members = _member_lookup(self.coordinator.data)
        open_items: list[dict[str, Any]] = []

        for item in self.coordinator.data.get("shopping_items", []):
            if item.get("status") != "open":
                continue

            added_at_raw = item.get("added_at")
            added_at = _parse_datetime_local(added_at_raw)
            added_at_local = added_at.isoformat() if isinstance(added_at, datetime) else None

            added_by_member_id = item.get("added_by_member_id")
            added_by_name = None
            if added_by_member_id is not None:
                try:
                    added_by_name = members.get(int(added_by_member_id))
                except (TypeError, ValueError):
                    added_by_name = None

            open_items.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "added_at": added_at_local or added_at_raw,
                    "added_by_member_id": added_by_member_id,
                    "added_by_name": added_by_name,
                }
            )

        open_items.sort(
            key=lambda row: (
                str(row.get("added_at") or ""),
                str(row.get("name") or "").lower(),
            )
        )

        favorites = [
            {"id": item.get("id"), "name": item.get("name")}
            for item in self.coordinator.data.get("shopping_favorites", [])
            if item.get("id") is not None and item.get("name")
        ]
        favorites.sort(key=lambda row: str(row["name"]).lower())

        recents = [str(item) for item in self.coordinator.data.get("shopping_recents", []) if item]
        suggestions = []
        seen: set[str] = set()
        for name in recents:
            key = str(name).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            suggestions.append(name)

        return {
            "open_items": open_items,
            "favorites": favorites,
            "recents": recents,
            "suggestions": suggestions[:40],
            "service_domain": DOMAIN,
            "service_add_item": SERVICE_ADD_SHOPPING_ITEM,
            "service_complete_item": SERVICE_COMPLETE_SHOPPING_ITEM,
            "service_delete_item": SERVICE_DELETE_SHOPPING_ITEM,
            "service_add_favorite": SERVICE_ADD_FAVORITE_ITEM,
            "service_delete_favorite": SERVICE_DELETE_FAVORITE_ITEM,
        }


class CleaningCurrentAssigneeSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Current Assignee"
    _attr_unique_id = "hass_flatmate_cleaning_current_assignee"
    _attr_icon = "mdi:broom"

    @property
    def native_value(self) -> str | None:
        current = self.coordinator.data.get("cleaning_current", {})
        member_id = current.get("effective_assignee_member_id")
        if member_id is None:
            return None
        return _member_lookup(self.coordinator.data).get(int(member_id), f"Member {member_id}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self.coordinator.data.get("cleaning_current", {})
        return {
            "week_start": current.get("week_start"),
            "effective_assignee_member_id": current.get("effective_assignee_member_id"),
            "baseline_assignee_member_id": current.get("baseline_assignee_member_id"),
        }


class CleaningCurrentStatusSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Current Week Status"
    _attr_unique_id = "hass_flatmate_cleaning_current_week_status"
    _attr_icon = "mdi:check-decagram-outline"

    @property
    def native_value(self) -> str | None:
        current = self.coordinator.data.get("cleaning_current", {})
        status = current.get("status")
        return str(status) if status is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current = self.coordinator.data.get("cleaning_current", {})
        return {
            "week_start": current.get("week_start"),
            "completed_by_member_id": current.get("completed_by_member_id"),
        }


class CleaningNextAssigneeSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Next Assignee"
    _attr_unique_id = "hass_flatmate_cleaning_next_assignee"
    _attr_icon = "mdi:calendar-next"

    @property
    def native_value(self) -> str | None:
        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        if len(schedule) < 2:
            return None
        member_id = schedule[1].get("effective_assignee_member_id")
        if member_id is None:
            return None
        return _member_lookup(self.coordinator.data).get(int(member_id), f"Member {member_id}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        if len(schedule) < 2:
            return {}
        row = schedule[1]
        return {
            "week_start": row.get("week_start"),
            "effective_assignee_member_id": row.get("effective_assignee_member_id"),
            "baseline_assignee_member_id": row.get("baseline_assignee_member_id"),
            "override_type": row.get("override_type"),
        }


class CleaningScheduleSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Cleaning Schedule"
    _attr_unique_id = "hass_flatmate_cleaning_schedule"
    _attr_icon = "mdi:calendar-range"

    @property
    def native_value(self) -> int:
        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        return len(schedule)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        members = _member_lookup(self.coordinator.data)
        members_payload = [
            {
                "member_id": int(member.get("id")),
                "name": member.get("display_name"),
                "ha_user_id": member.get("ha_user_id"),
            }
            for member in self.coordinator.data.get("members", [])
            if member.get("id") is not None and member.get("display_name") and member.get("active", True)
        ]
        members_payload.sort(key=lambda row: str(row["name"]).lower())

        member_user_lookup: dict[int, str | None] = {}
        for member in self.coordinator.data.get("members", []):
            if member.get("id") is None:
                continue
            if not member.get("active", True):
                continue
            try:
                member_id = int(member.get("id"))
            except (TypeError, ValueError):
                continue
            user_id = member.get("ha_user_id")
            member_user_lookup[member_id] = str(user_id) if user_id is not None else None

        schedule = self.coordinator.data.get("cleaning_schedule", {}).get("schedule", [])
        current = self.coordinator.data.get("cleaning_current", {})
        current_week_start = str(current.get("week_start") or "")
        current_week_start_date = _parse_date(current_week_start)
        current_status = current.get("status")
        current_completed_by_id = current.get("completed_by_member_id")
        history_by_week = _build_cleaning_history_by_week(
            self.coordinator.data.get("activity", []),
            members=members,
        )

        weeks = []
        for row in schedule:
            week_start = _parse_date(row.get("week_start"))
            if week_start is None:
                continue

            week_end = week_start + timedelta(days=6)
            effective_id = row.get("effective_assignee_member_id")
            baseline_id = row.get("baseline_assignee_member_id")
            override_type = row.get("override_type")
            override_source = row.get("override_source")

            assignee_name = None
            baseline_name = None
            if effective_id is not None:
                try:
                    assignee_name = members.get(int(effective_id))
                except (TypeError, ValueError):
                    assignee_name = None
            if baseline_id is not None:
                try:
                    baseline_name = members.get(int(baseline_id))
                except (TypeError, ValueError):
                    baseline_name = None

            note = ""
            if override_type == "manual_swap":
                note = "swap"
            elif override_type == "compensation":
                note = "swap return week" if override_source == "manual" else "make-up shift"

            is_current = week_start.isoformat() == current_week_start
            status_value = row.get("status")
            if status_value is None and is_current:
                status_value = current_status

            completed_by_member_id = row.get("completed_by_member_id")
            if completed_by_member_id is None and is_current:
                completed_by_member_id = current_completed_by_id
            completed_at = _parse_datetime_local(row.get("completed_at"))

            completed_by_name = None
            if completed_by_member_id is not None:
                try:
                    completed_by_name = members.get(int(completed_by_member_id))
                except (TypeError, ValueError):
                    completed_by_name = None

            is_past = (
                current_week_start_date is not None
                and week_start < current_week_start_date
            )
            is_previous = (
                current_week_start_date is not None
                and week_start == (current_week_start_date - timedelta(days=7))
            )
            is_next = (
                current_week_start_date is not None
                and week_start == (current_week_start_date + timedelta(days=7))
            )
            assignee_user_id = None
            if effective_id is not None:
                try:
                    assignee_user_id = member_user_lookup.get(int(effective_id))
                except (TypeError, ValueError):
                    assignee_user_id = None
            original_assignee_user_id = None
            if baseline_id is not None:
                try:
                    original_assignee_user_id = member_user_lookup.get(int(baseline_id))
                except (TypeError, ValueError):
                    original_assignee_user_id = None
            week_start_iso = week_start.isoformat()
            week_history = history_by_week.get(week_start_iso, [])
            notification_slots = _notification_slots_for_week(
                week_start=week_start,
                completed_at=completed_at,
                week_status=status_value,
                history=week_history,
            )
            notification_has_issue = any(
                slot.get("state") in {"failed", "skipped", "suppressed", "missing"}
                for slot in notification_slots
            )
            timeline = _build_week_timeline(
                notification_slots=notification_slots,
                history=week_history,
            )
            weeks.append(
                {
                    "week_start": week_start_iso,
                    "week_end": week_end.isoformat(),
                    "week_number": week_start.isocalendar().week,
                    "assignee_member_id": effective_id,
                    "assignee_name": assignee_name,
                    "assignee_user_id": assignee_user_id,
                    "original_assignee_member_id": baseline_id,
                    "original_assignee_name": baseline_name,
                    "original_assignee_user_id": original_assignee_user_id,
                    "baseline_assignee_member_id": baseline_id,
                    "baseline_assignee_name": baseline_name,
                    "override_type": override_type,
                    "override_source": override_source,
                    "source_week_start": row.get("source_week_start"),
                    "note": note,
                    "is_current": is_current,
                    "is_past": is_past,
                    "is_previous": is_previous,
                    "is_next": is_next,
                    "status": status_value,
                    "completed_by_member_id": completed_by_member_id,
                    "completed_by_name": completed_by_name,
                    "completion_mode": row.get("completion_mode"),
                    "completed_at": completed_at.isoformat() if completed_at is not None else row.get("completed_at"),
                    "history": week_history,
                    "notification_slots": notification_slots,
                    "notification_has_issue": notification_has_issue,
                    "timeline": timeline,
                }
            )

        return {
            "weeks": weeks,
            "members": members_payload,
            "service_domain": DOMAIN,
            "service_mark_done": SERVICE_MARK_CLEANING_DONE,
            "service_mark_undone": SERVICE_MARK_CLEANING_UNDONE,
            "service_mark_takeover_done": SERVICE_MARK_CLEANING_TAKEOVER_DONE,
            "service_swap_week": SERVICE_SWAP_CLEANING_WEEK,
        }


class ActivityRecentSensor(HassFlatmateCoordinatorEntity, SensorEntity):
    _attr_name = "Activity Recent"
    _attr_unique_id = "hass_flatmate_activity_recent"
    _attr_icon = "mdi:history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        events = self.coordinator.data.get("activity", [])
        return len(events)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        events = self.coordinator.data.get("activity", [])
        members = _member_lookup(self.coordinator.data)
        human = []
        for row in events[:20]:
            if not isinstance(row, Mapping):
                continue
            created = _parse_datetime_local(row.get("created_at"))
            human.append(
                {
                    "id": row.get("id"),
                    "created_at": created.isoformat() if created else row.get("created_at"),
                    "summary": _activity_summary(row, members),
                    "action": row.get("action"),
                }
            )
        return {
            "recent": events[:20],
            "recent_human": human,
        }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = get_runtime(entry, hass)

    async_add_entities(
        [
            ShoppingOpenCountSensor(entry, runtime),
            ShoppingDistributionSensor(entry, runtime),
            ShoppingDataSensor(entry, runtime),
            CleaningCurrentAssigneeSensor(entry, runtime),
            CleaningCurrentStatusSensor(entry, runtime),
            CleaningNextAssigneeSensor(entry, runtime),
            CleaningScheduleSensor(entry, runtime),
            ActivityRecentSensor(entry, runtime),
        ]
    )
