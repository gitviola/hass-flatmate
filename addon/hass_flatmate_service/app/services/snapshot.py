"""Full-state snapshot export/import helpers for migration workflows."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    ActivityEvent,
    CleaningAssignment,
    CleaningAssignmentStatus,
    CleaningOverride,
    Member,
    OverrideSource,
    OverrideStatus,
    OverrideType,
    RotationConfig,
    ShoppingFavorite,
    ShoppingItem,
    ShoppingStatus,
)
from ..services.time_utils import now_utc


_SNAPSHOT_SCHEMA_VERSION = 1


def _parse_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO date string")
    try:
        return date.fromisoformat(value.strip().split("T", maxsplit=1)[0])
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO date") from exc


def _parse_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO datetime string")

    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a valid ISO datetime") from exc


def _as_iso(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _export_rows(rows: list[Any], fields: list[str]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                field: _as_iso(getattr(row, field))
                for field in fields
            }
        )
    return payload


def export_snapshot(session: Session) -> dict[str, Any]:
    members = session.execute(select(Member).order_by(Member.id.asc())).scalars().all()
    rotation = session.get(RotationConfig, 1)
    cleaning_assignments = session.execute(
        select(CleaningAssignment).order_by(CleaningAssignment.week_start.asc())
    ).scalars().all()
    cleaning_overrides = session.execute(
        select(CleaningOverride).order_by(CleaningOverride.week_start.asc(), CleaningOverride.id.asc())
    ).scalars().all()
    shopping_items = session.execute(select(ShoppingItem).order_by(ShoppingItem.id.asc())).scalars().all()
    shopping_favorites = session.execute(select(ShoppingFavorite).order_by(ShoppingFavorite.id.asc())).scalars().all()
    activity_events = session.execute(select(ActivityEvent).order_by(ActivityEvent.id.asc())).scalars().all()

    data: dict[str, Any] = {
        "members": _export_rows(
            members,
            [
                "id",
                "display_name",
                "ha_user_id",
                "ha_person_entity_id",
                "notify_service",
                "notify_services",
                "device_trackers",
                "active",
                "created_at",
                "updated_at",
            ],
        ),
        "rotation_config": None,
        "cleaning_assignments": _export_rows(
            cleaning_assignments,
            [
                "week_start",
                "assignee_member_id",
                "status",
                "completed_by_member_id",
                "completion_mode",
                "completed_at",
                "notified_slots",
            ],
        ),
        "cleaning_overrides": _export_rows(
            cleaning_overrides,
            [
                "id",
                "week_start",
                "type",
                "source",
                "source_event_id",
                "member_from_id",
                "member_to_id",
                "status",
                "created_by_member_id",
                "created_at",
                "updated_at",
            ],
        ),
        "shopping_items": _export_rows(
            shopping_items,
            [
                "id",
                "name",
                "status",
                "added_by_member_id",
                "added_by_user_id_raw",
                "added_at",
                "completed_by_member_id",
                "completed_by_user_id_raw",
                "completed_at",
                "deleted_by_member_id",
                "deleted_by_user_id_raw",
                "deleted_at",
            ],
        ),
        "shopping_favorites": _export_rows(
            shopping_favorites,
            [
                "id",
                "name",
                "active",
                "created_by_member_id",
                "created_by_user_id_raw",
                "created_at",
            ],
        ),
        "activity_events": _export_rows(
            activity_events,
            [
                "id",
                "domain",
                "action",
                "actor_member_id",
                "actor_user_id_raw",
                "payload_json",
                "created_at",
            ],
        ),
    }

    if rotation is not None:
        data["rotation_config"] = {
            "id": rotation.id,
            "ordered_member_ids_json": list(rotation.ordered_member_ids_json or []),
            "anchor_week_start": _as_iso(rotation.anchor_week_start),
            "updated_at": _as_iso(rotation.updated_at),
        }

    summary = {
        "members": len(data["members"]),
        "cleaning_assignments": len(data["cleaning_assignments"]),
        "cleaning_overrides": len(data["cleaning_overrides"]),
        "shopping_items": len(data["shopping_items"]),
        "shopping_favorites": len(data["shopping_favorites"]),
        "activity_events": len(data["activity_events"]),
    }
    if data["rotation_config"] is not None:
        summary["rotation_config"] = 1
    else:
        summary["rotation_config"] = 0

    return {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "generated_at": now_utc().isoformat(),
        "summary": summary,
        "data": data,
    }


def _require_rows(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = data.get(key, [])
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError(f"snapshot data field '{key}' must be a list")
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"snapshot data field '{key}' row {index} must be an object")
        normalized.append(row)
    return normalized


def _clear_all_data(session: Session) -> None:
    session.execute(delete(CleaningOverride))
    session.execute(delete(CleaningAssignment))
    session.execute(delete(ActivityEvent))
    session.execute(delete(ShoppingItem))
    session.execute(delete(ShoppingFavorite))
    session.execute(delete(RotationConfig))
    session.execute(delete(Member))


def import_snapshot(
    session: Session,
    *,
    snapshot: dict[str, Any],
    replace_existing: bool,
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")

    schema_version = snapshot.get("schema_version")
    if schema_version not in (None, _SNAPSHOT_SCHEMA_VERSION):
        raise ValueError(
            f"Unsupported snapshot schema_version '{schema_version}'. "
            f"Supported version: {_SNAPSHOT_SCHEMA_VERSION}"
        )

    data_raw = snapshot.get("data", snapshot)
    if not isinstance(data_raw, dict):
        raise ValueError("snapshot.data must be an object")

    members_rows = _require_rows(data_raw, "members")
    assignment_rows = _require_rows(data_raw, "cleaning_assignments")
    override_rows = _require_rows(data_raw, "cleaning_overrides")
    shopping_item_rows = _require_rows(data_raw, "shopping_items")
    shopping_favorite_rows = _require_rows(data_raw, "shopping_favorites")
    activity_rows = _require_rows(data_raw, "activity_events")
    rotation_raw = data_raw.get("rotation_config")

    if rotation_raw is not None and not isinstance(rotation_raw, dict):
        raise ValueError("snapshot data field 'rotation_config' must be an object or null")

    if replace_existing:
        _clear_all_data(session)

    for row in members_rows:
        member_id = row.get("id")
        if member_id is None:
            raise ValueError("snapshot members rows require an 'id'")
        session.add(
            Member(
                id=int(member_id),
                display_name=str(row.get("display_name") or "").strip(),
                ha_user_id=row.get("ha_user_id"),
                ha_person_entity_id=row.get("ha_person_entity_id"),
                notify_service=row.get("notify_service"),
                notify_services=[str(value) for value in list(row.get("notify_services") or []) if str(value)],
                device_trackers=[str(value) for value in list(row.get("device_trackers") or []) if str(value)],
                active=bool(row.get("active", True)),
                created_at=_parse_datetime(
                    row.get("created_at") or now_utc().isoformat(),
                    field_name="members.created_at",
                ),
                updated_at=_parse_datetime(
                    row.get("updated_at") or now_utc().isoformat(),
                    field_name="members.updated_at",
                ),
            )
        )

    if rotation_raw is not None:
        anchor_week_start = rotation_raw.get("anchor_week_start")
        session.add(
            RotationConfig(
                id=int(rotation_raw.get("id", 1)),
                ordered_member_ids_json=[
                    int(member_id)
                    for member_id in list(rotation_raw.get("ordered_member_ids_json") or [])
                ],
                anchor_week_start=(
                    _parse_date(anchor_week_start, field_name="rotation_config.anchor_week_start")
                    if anchor_week_start is not None
                    else None
                ),
                updated_at=_parse_datetime(
                    rotation_raw.get("updated_at") or now_utc().isoformat(),
                    field_name="rotation_config.updated_at",
                ),
            )
        )

    for row in shopping_favorite_rows:
        favorite_id = row.get("id")
        if favorite_id is None:
            raise ValueError("snapshot shopping_favorites rows require an 'id'")
        session.add(
            ShoppingFavorite(
                id=int(favorite_id),
                name=str(row.get("name") or "").strip(),
                active=bool(row.get("active", True)),
                created_by_member_id=(
                    int(row["created_by_member_id"])
                    if row.get("created_by_member_id") is not None
                    else None
                ),
                created_by_user_id_raw=row.get("created_by_user_id_raw"),
                created_at=_parse_datetime(
                    row.get("created_at") or now_utc().isoformat(),
                    field_name="shopping_favorites.created_at",
                ),
            )
        )

    for row in shopping_item_rows:
        item_id = row.get("id")
        if item_id is None:
            raise ValueError("snapshot shopping_items rows require an 'id'")
        session.add(
            ShoppingItem(
                id=int(item_id),
                name=str(row.get("name") or "").strip(),
                status=ShoppingStatus(str(row.get("status"))),
                added_by_member_id=(
                    int(row["added_by_member_id"])
                    if row.get("added_by_member_id") is not None
                    else None
                ),
                added_by_user_id_raw=row.get("added_by_user_id_raw"),
                added_at=_parse_datetime(
                    row.get("added_at") or now_utc().isoformat(),
                    field_name="shopping_items.added_at",
                ),
                completed_by_member_id=(
                    int(row["completed_by_member_id"])
                    if row.get("completed_by_member_id") is not None
                    else None
                ),
                completed_by_user_id_raw=row.get("completed_by_user_id_raw"),
                completed_at=(
                    _parse_datetime(
                        row.get("completed_at"),
                        field_name="shopping_items.completed_at",
                    )
                    if row.get("completed_at") is not None
                    else None
                ),
                deleted_by_member_id=(
                    int(row["deleted_by_member_id"])
                    if row.get("deleted_by_member_id") is not None
                    else None
                ),
                deleted_by_user_id_raw=row.get("deleted_by_user_id_raw"),
                deleted_at=(
                    _parse_datetime(
                        row.get("deleted_at"),
                        field_name="shopping_items.deleted_at",
                    )
                    if row.get("deleted_at") is not None
                    else None
                ),
            )
        )

    for row in activity_rows:
        event_id = row.get("id")
        if event_id is None:
            raise ValueError("snapshot activity_events rows require an 'id'")
        payload_json = row.get("payload_json", {})
        if not isinstance(payload_json, dict):
            raise ValueError("snapshot activity_events payload_json must be an object")
        session.add(
            ActivityEvent(
                id=int(event_id),
                domain=str(row.get("domain") or "").strip(),
                action=str(row.get("action") or "").strip(),
                actor_member_id=(
                    int(row["actor_member_id"])
                    if row.get("actor_member_id") is not None
                    else None
                ),
                actor_user_id_raw=row.get("actor_user_id_raw"),
                payload_json=payload_json,
                created_at=_parse_datetime(
                    row.get("created_at") or now_utc().isoformat(),
                    field_name="activity_events.created_at",
                ),
            )
        )

    for row in override_rows:
        override_id = row.get("id")
        if override_id is None:
            raise ValueError("snapshot cleaning_overrides rows require an 'id'")
        session.add(
            CleaningOverride(
                id=int(override_id),
                week_start=_parse_date(row.get("week_start"), field_name="cleaning_overrides.week_start"),
                type=OverrideType(str(row.get("type"))),
                source=OverrideSource(str(row.get("source"))),
                source_event_id=(
                    int(row["source_event_id"])
                    if row.get("source_event_id") is not None
                    else None
                ),
                member_from_id=int(row.get("member_from_id")),
                member_to_id=int(row.get("member_to_id")),
                status=OverrideStatus(str(row.get("status"))),
                created_by_member_id=(
                    int(row["created_by_member_id"])
                    if row.get("created_by_member_id") is not None
                    else None
                ),
                created_at=_parse_datetime(
                    row.get("created_at") or now_utc().isoformat(),
                    field_name="cleaning_overrides.created_at",
                ),
                updated_at=_parse_datetime(
                    row.get("updated_at") or now_utc().isoformat(),
                    field_name="cleaning_overrides.updated_at",
                ),
            )
        )

    for row in assignment_rows:
        session.add(
            CleaningAssignment(
                week_start=_parse_date(row.get("week_start"), field_name="cleaning_assignments.week_start"),
                assignee_member_id=(
                    int(row["assignee_member_id"])
                    if row.get("assignee_member_id") is not None
                    else None
                ),
                status=CleaningAssignmentStatus(str(row.get("status"))),
                completed_by_member_id=(
                    int(row["completed_by_member_id"])
                    if row.get("completed_by_member_id") is not None
                    else None
                ),
                completion_mode=row.get("completion_mode"),
                completed_at=(
                    _parse_datetime(
                        row.get("completed_at"),
                        field_name="cleaning_assignments.completed_at",
                    )
                    if row.get("completed_at") is not None
                    else None
                ),
                notified_slots=(
                    row.get("notified_slots")
                    if isinstance(row.get("notified_slots"), dict) or row.get("notified_slots") is None
                    else None
                ),
            )
        )

    session.commit()

    return {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "replace_existing": replace_existing,
        "summary": {
            "members": len(members_rows),
            "rotation_config": 1 if rotation_raw is not None else 0,
            "cleaning_assignments": len(assignment_rows),
            "cleaning_overrides": len(override_rows),
            "shopping_items": len(shopping_item_rows),
            "shopping_favorites": len(shopping_favorite_rows),
            "activity_events": len(activity_rows),
        },
    }
