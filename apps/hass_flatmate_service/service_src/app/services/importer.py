"""Import helpers for manually migrating rotation/history data into hass-flatmate."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CleaningAssignmentStatus,
    CleaningOverride,
    OverrideSource,
    OverrideStatus,
    OverrideType,
    ShoppingItem,
    ShoppingStatus,
)
from ..services.activity import log_event
from ..services.cleaning import (
    ensure_assignment,
    get_or_create_rotation_config,
)
from ..services.members import get_active_members
from ..services.time_utils import monday_for, now_utc


def _normalize_member_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _rows_from_text(value: str | None) -> list[tuple[int, str]]:
    if value is None:
        return []
    expanded = value.replace(";", "\n")
    rows: list[tuple[int, str]] = []
    for line_no, raw in enumerate(expanded.splitlines(), start=1):
        row = raw.strip()
        if not row or row.startswith("#"):
            continue
        rows.append((line_no, row))
    return rows


def _parse_date_or_datetime(token: str, *, line_no: int) -> tuple[date, datetime]:
    value = token.strip()
    if not value:
        raise ValueError(f"Missing date value at row {line_no}")

    try:
        if "T" in value or " " in value:
            iso = value if "T" in value else value.replace(" ", "T", 1)
            parsed_dt = datetime.fromisoformat(iso)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            else:
                parsed_dt = parsed_dt.astimezone(timezone.utc)
            return parsed_dt.date(), parsed_dt

        parsed_date = date.fromisoformat(value)
        parsed_dt = datetime.combine(parsed_date, time(hour=12, tzinfo=timezone.utc))
        return parsed_date, parsed_dt
    except ValueError as exc:
        raise ValueError(f"Invalid date or datetime '{token}' at row {line_no}") from exc


def _member_index(session: Session) -> tuple[dict[str, int], list[int], dict[int, str]]:
    active_members = get_active_members(session)
    if not active_members:
        raise ValueError("No active members found. Sync members first.")

    index: dict[str, int] = {}
    id_to_name: dict[int, str] = {}
    for member in active_members:
        key = _normalize_member_name(member.display_name)
        if key in index and index[key] != member.id:
            raise ValueError(
                "Ambiguous member names detected among active flatmates. "
                "Rename members so names are unique for migration."
            )
        index[key] = member.id
        id_to_name[member.id] = member.display_name

    active_member_ids = [member.id for member in active_members]
    return index, active_member_ids, id_to_name


def _resolve_member_id(name_index: dict[str, int], raw_name: str, *, line_no: int) -> int:
    key = _normalize_member_name(raw_name)
    member_id = name_index.get(key)
    if member_id is None:
        raise ValueError(
            f"Unknown member '{raw_name}' at row {line_no}. "
            "Use exact display names from hass-flatmate members."
        )
    return member_id


def _apply_rotation_rows(
    session: Session,
    *,
    rows_text: str | None,
    name_index: dict[str, int],
    active_member_ids: list[int],
) -> tuple[date | None, list[int], int]:
    rows = _rows_from_text(rows_text)
    if not rows:
        return None, [], 0

    assignment_by_week: dict[date, int] = {}
    for line_no, row in rows:
        columns = [part.strip() for part in row.split(",")]
        if len(columns) < 2:
            raise ValueError(
                f"Rotation row {line_no} must contain at least 2 columns: "
                "date,member_name"
            )
        parsed_date, _parsed_dt = _parse_date_or_datetime(columns[0], line_no=line_no)
        week_start = monday_for(parsed_date)
        member_id = _resolve_member_id(name_index, columns[1], line_no=line_no)

        existing = assignment_by_week.get(week_start)
        if existing is not None and existing != member_id:
            raise ValueError(
                f"Conflicting rotation members for week {week_start.isoformat()} at row {line_no}"
            )
        assignment_by_week[week_start] = member_id

    sorted_weeks = sorted(assignment_by_week.keys())
    imported_order: list[int] = []
    for week_start in sorted_weeks:
        member_id = assignment_by_week[week_start]
        if member_id not in imported_order:
            imported_order.append(member_id)

    config = get_or_create_rotation_config(session)
    existing_order = [
        member_id
        for member_id in (config.ordered_member_ids_json or [])
        if member_id in active_member_ids and member_id not in imported_order
    ]
    trailing = [
        member_id
        for member_id in active_member_ids
        if member_id not in imported_order and member_id not in existing_order
    ]
    final_order = imported_order + existing_order + trailing

    config.ordered_member_ids_json = final_order
    config.anchor_week_start = sorted_weeks[0]

    for week_start in sorted_weeks:
        ensure_assignment(session, week_start)

    return sorted_weeks[0], final_order, len(sorted_weeks)


def _apply_cleaning_history_rows(
    session: Session,
    *,
    rows_text: str | None,
    name_index: dict[str, int],
    actor_user_id: str | None,
) -> tuple[int, int]:
    rows = _rows_from_text(rows_text)
    if not rows:
        return 0, 0

    imported_rows = 0
    imported_done_events = 0

    for line_no, row in rows:
        columns = [part.strip() for part in row.split(",")]
        if len(columns) < 2:
            raise ValueError(
                f"Cleaning history row {line_no} must contain at least 2 columns: "
                "date,member_name[,status][,completed_by_name]"
            )

        parsed_date, at_dt = _parse_date_or_datetime(columns[0], line_no=line_no)
        week_start = monday_for(parsed_date)
        member_id = _resolve_member_id(name_index, columns[1], line_no=line_no)
        status_value = columns[2].strip().lower() if len(columns) >= 3 and columns[2].strip() else "done"

        assignment = ensure_assignment(session, week_start)
        imported_rows += 1

        if status_value == "done":
            completed_by_member_id = member_id
            if len(columns) >= 4 and columns[3].strip():
                completed_by_member_id = _resolve_member_id(name_index, columns[3], line_no=line_no)

            completion_mode = (
                "own" if assignment.assignee_member_id == completed_by_member_id else "takeover"
            )
            assignment.status = CleaningAssignmentStatus.DONE
            assignment.completed_by_member_id = completed_by_member_id
            assignment.completion_mode = completion_mode
            assignment.completed_at = at_dt

            payload: dict[str, Any] = {
                "week_start": week_start.isoformat(),
                "completed_by_member_id": completed_by_member_id,
                "completion_mode": completion_mode,
                "imported": True,
            }
            action = "cleaning_done"
            if completion_mode == "takeover":
                action = "cleaning_takeover_done"
                payload["cleaner_member_id"] = completed_by_member_id
                payload["original_assignee_member_id"] = assignment.assignee_member_id

            log_event(
                session,
                domain="cleaning",
                action=action,
                actor_member_id=completed_by_member_id,
                actor_user_id_raw=actor_user_id,
                payload=payload,
                created_at=at_dt,
            )
            imported_done_events += 1
            continue

        if status_value == "missed":
            assignment.status = CleaningAssignmentStatus.MISSED
            assignment.completed_by_member_id = None
            assignment.completion_mode = None
            assignment.completed_at = None
            continue

        if status_value == "pending":
            assignment.status = CleaningAssignmentStatus.PENDING
            assignment.completed_by_member_id = None
            assignment.completion_mode = None
            assignment.completed_at = None
            continue

        raise ValueError(
            f"Unsupported cleaning status '{status_value}' at row {line_no}. "
            "Allowed values: done, missed, pending"
        )

    return imported_rows, imported_done_events


def _apply_shopping_history_rows(
    session: Session,
    *,
    rows_text: str | None,
    name_index: dict[str, int],
    actor_user_id: str | None,
) -> int:
    rows = _rows_from_text(rows_text)
    if not rows:
        return 0

    imported_rows = 0

    for line_no, row in rows:
        columns = [part.strip() for part in row.split(",")]
        if len(columns) < 3:
            raise ValueError(
                f"Shopping history row {line_no} must contain at least 3 columns: "
                "date,item_name,buyer_name"
            )

        _parsed_date, at_dt = _parse_date_or_datetime(columns[0], line_no=line_no)
        item_name = columns[1].strip()
        if not item_name:
            raise ValueError(f"Missing shopping item name at row {line_no}")
        buyer_member_id = _resolve_member_id(name_index, columns[2], line_no=line_no)

        item = ShoppingItem(
            name=item_name,
            status=ShoppingStatus.COMPLETED,
            added_by_member_id=buyer_member_id,
            added_by_user_id_raw=None,
            added_at=at_dt,
            completed_by_member_id=buyer_member_id,
            completed_by_user_id_raw=None,
            completed_at=at_dt,
            deleted_by_member_id=None,
            deleted_by_user_id_raw=None,
            deleted_at=None,
        )
        session.add(item)
        session.flush()

        log_event(
            session,
            domain="shopping",
            action="shopping_item_completed",
            actor_member_id=buyer_member_id,
            actor_user_id_raw=actor_user_id,
            payload={"item_id": item.id, "name": item.name, "imported": True},
            created_at=at_dt,
        )
        imported_rows += 1

    return imported_rows


def _parse_override_type(token: str | None, *, line_no: int) -> OverrideType:
    raw = (token or "").strip().lower()
    if not raw or raw == "compensation":
        return OverrideType.COMPENSATION
    if raw in {"manual_swap", "swap"}:
        return OverrideType.MANUAL_SWAP
    raise ValueError(
        f"Unsupported override type '{token}' at row {line_no}. "
        "Allowed values: compensation, manual_swap"
    )


def _apply_cleaning_override_rows(
    session: Session,
    *,
    rows_text: str | None,
    name_index: dict[str, int],
    actor_user_id: str | None,
) -> tuple[int, int]:
    rows = _rows_from_text(rows_text)
    if not rows:
        return 0, 0

    imported_rows = 0
    imported_overrides: list[CleaningOverride] = []
    for line_no, row in rows:
        columns = [part.strip() for part in row.split(",")]
        if len(columns) < 3:
            raise ValueError(
                f"Cleaning override row {line_no} must contain at least 3 columns: "
                "date,member_from_name,member_to_name[,override_type]"
            )

        parsed_date, _at_dt = _parse_date_or_datetime(columns[0], line_no=line_no)
        week_start = monday_for(parsed_date)
        member_from_id = _resolve_member_id(name_index, columns[1], line_no=line_no)
        member_to_id = _resolve_member_id(name_index, columns[2], line_no=line_no)
        override_type = _parse_override_type(columns[3] if len(columns) >= 4 else None, line_no=line_no)

        if member_from_id == member_to_id:
            raise ValueError(
                f"Cleaning override row {line_no} must use two different members."
            )

        existing_planned = session.execute(
            select(CleaningOverride).where(
                CleaningOverride.week_start == week_start,
                CleaningOverride.status == OverrideStatus.PLANNED,
            )
        ).scalar_one_or_none()
        if existing_planned is not None:
            raise ValueError(
                f"Week {week_start.isoformat()} already has a planned override. "
                "Cancel existing override first or choose another week."
            )

        override = CleaningOverride(
            week_start=week_start,
            type=override_type,
            source=OverrideSource.MANUAL,
            source_event_id=None,
            member_from_id=member_from_id,
            member_to_id=member_to_id,
            status=OverrideStatus.PLANNED,
            created_by_member_id=None,
        )
        session.add(override)
        imported_overrides.append(override)
        ensure_assignment(session, week_start)
        imported_rows += 1

    linked_pairs = _link_imported_manual_swap_pairs(
        session,
        imported_overrides=imported_overrides,
        actor_user_id=actor_user_id,
    )

    return imported_rows, linked_pairs


def _link_imported_manual_swap_pairs(
    session: Session,
    *,
    imported_overrides: list[CleaningOverride],
    actor_user_id: str | None,
) -> int:
    if not imported_overrides:
        return 0

    manual_swaps = sorted(
        [
            override
            for override in imported_overrides
            if override.type == OverrideType.MANUAL_SWAP
            and override.source == OverrideSource.MANUAL
            and override.source_event_id is None
        ],
        key=lambda override: override.week_start,
    )
    if not manual_swaps:
        return 0

    compensation_by_pair: dict[tuple[int, int], list[CleaningOverride]] = {}
    for override in imported_overrides:
        if override.type != OverrideType.COMPENSATION:
            continue
        if override.source != OverrideSource.MANUAL:
            continue
        if override.source_event_id is not None:
            continue
        pair_key = (override.member_from_id, override.member_to_id)
        compensation_by_pair.setdefault(pair_key, []).append(override)

    for rows in compensation_by_pair.values():
        rows.sort(key=lambda override: override.week_start)

    linked_pairs = 0
    for swap_override in manual_swaps:
        compensation_key = (swap_override.member_to_id, swap_override.member_from_id)
        candidates = compensation_by_pair.get(compensation_key, [])
        if not candidates:
            continue

        match_index = -1
        match_override = None
        for index, candidate in enumerate(candidates):
            if candidate.week_start <= swap_override.week_start:
                continue
            match_index = index
            match_override = candidate
            break

        if match_override is None:
            continue

        imported_event_at = datetime.combine(swap_override.week_start, time(hour=12, tzinfo=timezone.utc))
        swap_event = log_event(
            session,
            domain="cleaning",
            action="cleaning_swap_created",
            actor_member_id=None,
            actor_user_id_raw=actor_user_id,
            payload={
                "week_start": swap_override.week_start.isoformat(),
                "member_a_id": swap_override.member_from_id,
                "member_b_id": swap_override.member_to_id,
                "return_week_start": match_override.week_start.isoformat(),
                "imported": True,
            },
            created_at=imported_event_at,
        )

        swap_override.source_event_id = swap_event.id
        match_override.source_event_id = swap_event.id
        candidates.pop(match_index)
        linked_pairs += 1

    return linked_pairs


def import_manual_data(
    session: Session,
    *,
    rotation_rows: str | None,
    cleaning_history_rows: str | None,
    shopping_history_rows: str | None,
    cleaning_override_rows: str | None,
    actor_user_id: str | None,
) -> tuple[dict[str, Any], list[dict]]:
    if not any(
        value and value.strip()
        for value in [rotation_rows, cleaning_history_rows, shopping_history_rows, cleaning_override_rows]
    ):
        raise ValueError("At least one import field must be provided")

    name_index, active_member_ids, id_to_name = _member_index(session)

    anchor_week_start, order_member_ids, rotation_weeks_imported = _apply_rotation_rows(
        session,
        rows_text=rotation_rows,
        name_index=name_index,
        active_member_ids=active_member_ids,
    )
    cleaning_rows_imported, cleaning_done_events_imported = _apply_cleaning_history_rows(
        session,
        rows_text=cleaning_history_rows,
        name_index=name_index,
        actor_user_id=actor_user_id,
    )
    shopping_rows_imported = _apply_shopping_history_rows(
        session,
        rows_text=shopping_history_rows,
        name_index=name_index,
        actor_user_id=actor_user_id,
    )
    cleaning_override_rows_imported, cleaning_override_swap_pairs_linked = _apply_cleaning_override_rows(
        session,
        rows_text=cleaning_override_rows,
        name_index=name_index,
        actor_user_id=actor_user_id,
    )

    summary = {
        "rotation_weeks_imported": rotation_weeks_imported,
        "rotation_anchor_week_start": anchor_week_start.isoformat() if anchor_week_start else None,
        "rotation_order_member_ids": order_member_ids,
        "rotation_order_names": [id_to_name.get(member_id, str(member_id)) for member_id in order_member_ids],
        "cleaning_history_rows_imported": cleaning_rows_imported,
        "cleaning_done_events_imported": cleaning_done_events_imported,
        "shopping_history_rows_imported": shopping_rows_imported,
        "cleaning_override_rows_imported": cleaning_override_rows_imported,
        "cleaning_override_swap_pairs_linked": cleaning_override_swap_pairs_linked,
    }

    log_event(
        session,
        domain="migration",
        action="manual_import_applied",
        actor_member_id=None,
        actor_user_id_raw=actor_user_id,
        payload=summary,
        created_at=now_utc(),
    )

    session.commit()
    return summary, []


def import_flatastic_data(
    session: Session,
    *,
    rotation_rows: str | None,
    cleaning_history_rows: str | None,
    shopping_history_rows: str | None,
    cleaning_override_rows: str | None,
    actor_user_id: str | None,
) -> tuple[dict[str, Any], list[dict]]:
    """Backward-compat alias; use import_manual_data."""
    return import_manual_data(
        session,
        rotation_rows=rotation_rows,
        cleaning_history_rows=cleaning_history_rows,
        shopping_history_rows=shopping_history_rows,
        cleaning_override_rows=cleaning_override_rows,
        actor_user_id=actor_user_id,
    )
