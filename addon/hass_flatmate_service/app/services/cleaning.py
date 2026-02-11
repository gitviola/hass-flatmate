"""Cleaning rotation, overrides, and notifications logic."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
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
)
from ..services.activity import log_event
from ..services.members import get_active_members, get_member_by_id, resolve_actor_member
from ..services.time_utils import add_weeks, monday_for, now_utc, week_start_for


def _planned_override_for_week(session: Session, week_start: date) -> CleaningOverride | None:
    return session.execute(
        select(CleaningOverride)
        .where(
            CleaningOverride.week_start == week_start,
            CleaningOverride.status == OverrideStatus.PLANNED,
        )
        .order_by(CleaningOverride.created_at.asc())
    ).scalar_one_or_none()


def _ensure_week_start_is_monday(week_start: date) -> None:
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday date")


def get_or_create_rotation_config(session: Session) -> RotationConfig:
    config = session.get(RotationConfig, 1)
    if config is None:
        config = RotationConfig(id=1, ordered_member_ids_json=[], anchor_week_start=None)
        session.add(config)
        session.flush()
    return config


def sync_rotation_members(session: Session) -> RotationConfig:
    config = get_or_create_rotation_config(session)
    active_members = get_active_members(session)
    active_ids = [m.id for m in active_members]

    if not config.ordered_member_ids_json:
        config.ordered_member_ids_json = active_ids
        config.anchor_week_start = monday_for(now_utc().date())
        session.commit()
        return config

    preserved = [member_id for member_id in config.ordered_member_ids_json if member_id in active_ids]
    new_members = [member_id for member_id in active_ids if member_id not in preserved]
    config.ordered_member_ids_json = preserved + new_members

    if config.anchor_week_start is None:
        config.anchor_week_start = monday_for(now_utc().date())

    session.commit()
    return config


def baseline_assignee_member_id(session: Session, week_start: date) -> int | None:
    config = sync_rotation_members(session)
    ordered = config.ordered_member_ids_json

    if not ordered:
        return None

    anchor = config.anchor_week_start or week_start
    delta_weeks = (week_start - anchor).days // 7
    idx = delta_weeks % len(ordered)
    return ordered[idx]


def _apply_override(assignee_member_id: int | None, override: CleaningOverride | None) -> int | None:
    if assignee_member_id is None or override is None:
        return assignee_member_id

    if override.type == OverrideType.MANUAL_SWAP:
        if assignee_member_id == override.member_from_id:
            return override.member_to_id
        if assignee_member_id == override.member_to_id:
            return override.member_from_id
        return assignee_member_id

    if override.type == OverrideType.COMPENSATION:
        if assignee_member_id == override.member_from_id:
            return override.member_to_id

    return assignee_member_id


def effective_assignee_member_id(session: Session, week_start: date) -> tuple[int | None, CleaningOverride | None]:
    baseline_id = baseline_assignee_member_id(session, week_start)
    override = _planned_override_for_week(session, week_start)
    return _apply_override(baseline_id, override), override


def ensure_assignment(session: Session, week_start: date) -> CleaningAssignment:
    assignment = session.get(CleaningAssignment, week_start)
    effective_id, _ = effective_assignee_member_id(session, week_start)

    if assignment is None:
        assignment = CleaningAssignment(
            week_start=week_start,
            assignee_member_id=effective_id,
            status=CleaningAssignmentStatus.PENDING,
        )
        session.add(assignment)
        session.flush()
        return assignment

    if assignment.status == CleaningAssignmentStatus.PENDING:
        assignment.assignee_member_id = effective_id

    return assignment


def mark_past_pending_as_missed(session: Session, current_week_start: date) -> None:
    rows = session.execute(
        select(CleaningAssignment).where(
            CleaningAssignment.week_start < current_week_start,
            CleaningAssignment.status == CleaningAssignmentStatus.PENDING,
        )
    ).scalars().all()
    for row in rows:
        row.status = CleaningAssignmentStatus.MISSED


def _member_notification(member: Member | None, title: str, message: str) -> dict:
    return {
        "member_id": member.id if member else None,
        "notify_service": member.notify_service if member else None,
        "title": title,
        "message": message,
    }


def _build_swap_notifications(
    session: Session,
    member_a_id: int,
    member_b_id: int,
    week_start: date,
    *,
    action: str,
) -> list[dict]:
    member_a = get_member_by_id(session, member_a_id)
    member_b = get_member_by_id(session, member_b_id)
    original_assignee_id = baseline_assignee_member_id(session, week_start)
    original_assignee = (
        get_member_by_id(session, original_assignee_id)
        if original_assignee_id is not None
        else None
    )
    original_suffix = (
        f" Original assignee: {original_assignee.display_name}."
        if original_assignee is not None
        else ""
    )

    if action == "created":
        msg_a = (
            f"Swap confirmed for week {week_start.isoformat()} with "
            f"{member_b.display_name if member_b else 'member'}."
            f"{original_suffix}"
        )
        msg_b = (
            f"Swap confirmed for week {week_start.isoformat()} with "
            f"{member_a.display_name if member_a else 'member'}."
            f"{original_suffix}"
        )
    elif action == "updated":
        msg_a = f"Swap updated for week {week_start.isoformat()}. Check current assignment.{original_suffix}"
        msg_b = f"Swap updated for week {week_start.isoformat()}. Check current assignment.{original_suffix}"
    else:
        msg_a = f"Swap canceled for week {week_start.isoformat()}. Rotation has been restored.{original_suffix}"
        msg_b = f"Swap canceled for week {week_start.isoformat()}. Rotation has been restored.{original_suffix}"

    title = "Weekly Cleaning Shift"
    return [
        _member_notification(member_a, title, msg_a),
        _member_notification(member_b, title, msg_b),
    ]


def upsert_manual_swap(
    session: Session,
    *,
    week_start: date,
    member_a_id: int,
    member_b_id: int,
    actor_user_id: str | None,
    cancel: bool,
) -> tuple[CleaningOverride | None, list[dict]]:
    _ensure_week_start_is_monday(week_start)
    if not cancel and member_a_id == member_b_id:
        raise ValueError("member_a_id and member_b_id must be different")

    actor_member = resolve_actor_member(session, actor_user_id)
    existing_any = _planned_override_for_week(session, week_start)
    existing = existing_any if existing_any and existing_any.type == OverrideType.MANUAL_SWAP else None

    notifications: list[dict] = []
    action = "created"

    if cancel:
        if existing is not None:
            already_canceled = session.execute(
                select(CleaningOverride).where(
                    CleaningOverride.week_start == week_start,
                    CleaningOverride.type == OverrideType.MANUAL_SWAP,
                    CleaningOverride.status == OverrideStatus.CANCELED,
                )
            ).scalar_one_or_none()

            if already_canceled is not None and already_canceled.id != existing.id:
                already_canceled.member_from_id = existing.member_from_id
                already_canceled.member_to_id = existing.member_to_id
                already_canceled.created_by_member_id = actor_member.id if actor_member else None
                session.delete(existing)
            else:
                existing.status = OverrideStatus.CANCELED
            action = "canceled"
            notifications = _build_swap_notifications(
                session,
                existing.member_from_id,
                existing.member_to_id,
                week_start,
                action="canceled",
            )
            log_event(
                session,
                domain="cleaning",
                action="cleaning_swap_canceled",
                actor_member_id=actor_member.id if actor_member else None,
                actor_user_id_raw=actor_user_id,
                payload={
                    "week_start": week_start.isoformat(),
                    "member_a_id": existing.member_from_id,
                    "member_b_id": existing.member_to_id,
                },
            )
        session.flush()
        ensure_assignment(session, week_start)
        session.commit()
        return None, notifications

    if get_member_by_id(session, member_a_id) is None:
        raise ValueError("member_a_id not found")
    if get_member_by_id(session, member_b_id) is None:
        raise ValueError("member_b_id not found")

    if existing_any is not None and existing is None:
        raise ValueError("A planned override already exists for this week")

    if existing is None:
        existing = CleaningOverride(
            week_start=week_start,
            type=OverrideType.MANUAL_SWAP,
            source=OverrideSource.MANUAL,
            member_from_id=member_a_id,
            member_to_id=member_b_id,
            status=OverrideStatus.PLANNED,
            created_by_member_id=actor_member.id if actor_member else None,
        )
        session.add(existing)
        action = "created"
    else:
        existing.member_from_id = member_a_id
        existing.member_to_id = member_b_id
        action = "updated"

    ensure_assignment(session, week_start)

    notifications = _build_swap_notifications(
        session,
        member_a_id,
        member_b_id,
        week_start,
        action=action,
    )

    log_event(
        session,
        domain="cleaning",
        action=f"cleaning_swap_{action}",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={
            "week_start": week_start.isoformat(),
            "member_a_id": member_a_id,
            "member_b_id": member_b_id,
        },
    )

    session.commit()
    return existing, notifications


def _next_baseline_week_for_member(
    session: Session,
    member_id: int,
    *,
    start_week: date,
    max_scan_weeks: int = 156,
) -> date:
    candidate = start_week
    for _ in range(max_scan_weeks):
        baseline_id = baseline_assignee_member_id(session, candidate)
        override = _planned_override_for_week(session, candidate)
        if baseline_id == member_id and override is None:
            return candidate
        candidate = add_weeks(candidate, 1)

    raise ValueError("Could not find eligible compensation week")


def mark_cleaning_done(
    session: Session,
    *,
    week_start: date,
    actor_user_id: str | None,
    completed_by_member_id: int | None = None,
) -> list[dict]:
    _ensure_week_start_is_monday(week_start)
    actor_member = resolve_actor_member(session, actor_user_id)
    assignment = ensure_assignment(session, week_start)
    notifications: list[dict] = []

    completed_by_member = actor_member
    if completed_by_member_id is not None:
        completed_by_member = get_member_by_id(session, completed_by_member_id)
        if completed_by_member is None:
            raise ValueError("completed_by_member_id not found")
        if (
            assignment.assignee_member_id is not None
            and completed_by_member.id != assignment.assignee_member_id
        ):
            raise ValueError(
                "completed_by_member_id must match the assignee for mark_done; "
                "use mark_takeover_done for takeover completion"
            )

    now = now_utc()
    assignment.status = CleaningAssignmentStatus.DONE
    assignment.completed_by_member_id = completed_by_member.id if completed_by_member else None
    assignment.completion_mode = "own"
    assignment.completed_at = now

    override = _planned_override_for_week(session, week_start)
    if override is not None:
        override.status = OverrideStatus.APPLIED

    log_event(
        session,
        domain="cleaning",
        action="cleaning_done",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={
            "week_start": week_start.isoformat(),
            "completed_by_member_id": assignment.completed_by_member_id,
            "completion_mode": "own",
            "confirmed_by_member_id": actor_member.id if actor_member else None,
        },
        created_at=now,
    )

    if (
        actor_member is not None
        and completed_by_member is not None
        and actor_member.id != completed_by_member.id
    ):
        notifications.append(
            _member_notification(
                completed_by_member,
                "Weekly Cleaning Shift",
                (
                    f"{actor_member.display_name} marked your cleaning shift as done for week "
                    f"{week_start.isoformat()}."
                ),
            )
        )

    session.commit()
    return notifications


def _latest_takeover_event_for_week(session: Session, week_start: date) -> ActivityEvent | None:
    week_start_iso = week_start.isoformat()
    rows = session.execute(
        select(ActivityEvent)
        .where(
            ActivityEvent.domain == "cleaning",
            ActivityEvent.action == "cleaning_takeover_done",
        )
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
    ).scalars().all()

    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        if str(payload.get("week_start")) == week_start_iso:
            return row
    return None


def mark_cleaning_undone(
    session: Session,
    *,
    week_start: date,
    actor_user_id: str | None,
) -> None:
    _ensure_week_start_is_monday(week_start)
    actor_member = resolve_actor_member(session, actor_user_id)
    assignment = ensure_assignment(session, week_start)

    if assignment.status != CleaningAssignmentStatus.DONE:
        return

    previous_mode = assignment.completion_mode

    assignment.status = CleaningAssignmentStatus.PENDING
    assignment.completed_by_member_id = None
    assignment.completion_mode = None
    assignment.completed_at = None

    override = _planned_override_for_week(session, week_start)
    if override is None:
        override = session.execute(
            select(CleaningOverride).where(
                CleaningOverride.week_start == week_start,
                CleaningOverride.status == OverrideStatus.APPLIED,
            )
        ).scalar_one_or_none()
    if override is not None and override.status == OverrideStatus.APPLIED:
        override.status = OverrideStatus.PLANNED

    if previous_mode == "takeover":
        takeover_event = _latest_takeover_event_for_week(session, week_start)
        if takeover_event is not None:
            linked_compensations = session.execute(
                select(CleaningOverride).where(
                    CleaningOverride.source_event_id == takeover_event.id,
                    CleaningOverride.type == OverrideType.COMPENSATION,
                    CleaningOverride.status == OverrideStatus.PLANNED,
                )
            ).scalars().all()
            for compensation in linked_compensations:
                compensation.status = OverrideStatus.CANCELED

    log_event(
        session,
        domain="cleaning",
        action="cleaning_undone",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={
            "week_start": week_start.isoformat(),
            "previous_completion_mode": previous_mode,
        },
        created_at=now_utc(),
    )

    session.commit()


def _build_compensation_notifications(
    session: Session,
    *,
    week_start: date,
    member_from_id: int,
    member_to_id: int,
) -> list[dict]:
    member_from = get_member_by_id(session, member_from_id)
    member_to = get_member_by_id(session, member_to_id)

    title = "Weekly Cleaning Shift"
    msg_from = (
        f"Compensation override planned for week {week_start.isoformat()}: "
        f"{member_to.display_name if member_to else 'Another member'} will cover your turn."
    )
    msg_to = (
        f"Compensation override planned for week {week_start.isoformat()}: "
        f"you are scheduled to cover {member_from.display_name if member_from else 'another member'}'s turn."
    )
    return [
        _member_notification(member_from, title, msg_from),
        _member_notification(member_to, title, msg_to),
    ]


def _cancel_override_without_status_collision(
    session: Session,
    *,
    override: CleaningOverride,
    actor_member_id: int | None,
) -> None:
    existing_canceled = session.execute(
        select(CleaningOverride).where(
            CleaningOverride.week_start == override.week_start,
            CleaningOverride.status == OverrideStatus.CANCELED,
            CleaningOverride.id != override.id,
        )
    ).scalar_one_or_none()

    if existing_canceled is not None:
        existing_canceled.type = override.type
        existing_canceled.source = override.source
        existing_canceled.source_event_id = override.source_event_id
        existing_canceled.member_from_id = override.member_from_id
        existing_canceled.member_to_id = override.member_to_id
        existing_canceled.created_by_member_id = actor_member_id
        session.delete(override)
        return

    override.status = OverrideStatus.CANCELED


def _build_inactive_member_override_notifications(
    session: Session,
    *,
    override: CleaningOverride,
    inactive_member_ids: set[int],
) -> list[dict]:
    inactive_names = [
        member.display_name
        for member_id in sorted(inactive_member_ids)
        for member in [get_member_by_id(session, member_id)]
        if member is not None
    ]
    inactive_label = ", ".join(inactive_names) if inactive_names else "a former flatmate"

    if override.type == OverrideType.MANUAL_SWAP:
        message = (
            f"A planned cleaning swap for week {override.week_start.isoformat()} was canceled because "
            f"{inactive_label} is no longer active in the flat."
        )
    else:
        message = (
            f"A planned cleaning compensation for week {override.week_start.isoformat()} was canceled because "
            f"{inactive_label} is no longer active in the flat."
        )

    notifications: list[dict] = []
    for member_id in sorted({override.member_from_id, override.member_to_id} - inactive_member_ids):
        member = get_member_by_id(session, member_id)
        if member is None or not member.active:
            continue
        notifications.append(_member_notification(member, "Weekly Cleaning Shift", message))

    return notifications


def cancel_overrides_for_inactive_members(
    session: Session,
    *,
    inactive_member_ids: set[int],
    actor_user_id: str | None = None,
) -> list[dict]:
    if not inactive_member_ids:
        return []

    actor_member = resolve_actor_member(session, actor_user_id)
    overrides = session.execute(
        select(CleaningOverride)
        .where(
            CleaningOverride.status == OverrideStatus.PLANNED,
        )
        .order_by(CleaningOverride.week_start.asc(), CleaningOverride.created_at.asc())
    ).scalars().all()

    notifications: list[dict] = []
    affected_weeks: set[date] = set()

    for override in overrides:
        impacted_inactive = {override.member_from_id, override.member_to_id} & inactive_member_ids
        if not impacted_inactive:
            continue

        notifications.extend(
            _build_inactive_member_override_notifications(
                session,
                override=override,
                inactive_member_ids=impacted_inactive,
            )
        )

        _cancel_override_without_status_collision(
            session,
            override=override,
            actor_member_id=actor_member.id if actor_member else None,
        )
        affected_weeks.add(override.week_start)

        log_event(
            session,
            domain="cleaning",
            action="cleaning_override_auto_canceled_member_inactive",
            actor_member_id=actor_member.id if actor_member else None,
            actor_user_id_raw=actor_user_id,
            payload={
                "week_start": override.week_start.isoformat(),
                "override_type": override.type.value,
                "member_from_id": override.member_from_id,
                "member_to_id": override.member_to_id,
                "inactive_member_ids": sorted(impacted_inactive),
            },
            created_at=now_utc(),
        )

    for week_start in sorted(affected_weeks):
        ensure_assignment(session, week_start)

    session.commit()
    return notifications


def mark_cleaning_takeover_done(
    session: Session,
    *,
    week_start: date,
    original_assignee_member_id: int,
    cleaner_member_id: int,
    actor_user_id: str | None,
) -> list[dict]:
    _ensure_week_start_is_monday(week_start)
    if get_member_by_id(session, original_assignee_member_id) is None:
        raise ValueError("original_assignee_member_id not found")
    if get_member_by_id(session, cleaner_member_id) is None:
        raise ValueError("cleaner_member_id not found")

    actor_member = resolve_actor_member(session, actor_user_id)
    assignment = ensure_assignment(session, week_start)

    now = now_utc()
    assignment.status = CleaningAssignmentStatus.DONE
    assignment.completed_by_member_id = cleaner_member_id
    assignment.completion_mode = "takeover"
    assignment.completed_at = now

    override = _planned_override_for_week(session, week_start)
    if override is not None:
        override.status = OverrideStatus.APPLIED

    takeover_event = log_event(
        session,
        domain="cleaning",
        action="cleaning_takeover_done",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={
            "week_start": week_start.isoformat(),
            "original_assignee_member_id": original_assignee_member_id,
            "cleaner_member_id": cleaner_member_id,
            "completion_mode": "takeover",
        },
        created_at=now,
    )

    compensation_start = add_weeks(week_start, 1)
    compensation_week = _next_baseline_week_for_member(
        session,
        cleaner_member_id,
        start_week=compensation_start,
    )

    compensation = CleaningOverride(
        week_start=compensation_week,
        type=OverrideType.COMPENSATION,
        source=OverrideSource.TAKEOVER_COMPLETION,
        source_event_id=takeover_event.id,
        member_from_id=cleaner_member_id,
        member_to_id=original_assignee_member_id,
        status=OverrideStatus.PLANNED,
        created_by_member_id=actor_member.id if actor_member else None,
    )
    session.add(compensation)

    log_event(
        session,
        domain="cleaning",
        action="cleaning_compensation_planned",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={
            "source_week_start": week_start.isoformat(),
            "compensation_week_start": compensation_week.isoformat(),
            "member_from_id": cleaner_member_id,
            "member_to_id": original_assignee_member_id,
            "override_type": "compensation",
        },
    )

    ensure_assignment(session, compensation_week)

    notifications = _build_compensation_notifications(
        session,
        week_start=compensation_week,
        member_from_id=cleaner_member_id,
        member_to_id=original_assignee_member_id,
    )

    session.commit()
    return notifications


def get_cleaning_current(session: Session, at: datetime | None = None) -> dict:
    now = at or now_utc()
    week_start = week_start_for(now)
    mark_past_pending_as_missed(session, week_start)
    assignment = ensure_assignment(session, week_start)
    baseline_id = baseline_assignee_member_id(session, week_start)
    effective_id, _override = effective_assignee_member_id(session, week_start)
    session.commit()

    return {
        "week_start": week_start,
        "baseline_assignee_member_id": baseline_id,
        "effective_assignee_member_id": effective_id,
        "status": assignment.status.value,
        "completed_by_member_id": assignment.completed_by_member_id,
    }


def get_schedule(session: Session, *, weeks_ahead: int, from_week_start: date | None = None) -> list[dict]:
    start = from_week_start or week_start_for(now_utc())
    rows: list[dict] = []

    for offset in range(max(weeks_ahead, 0)):
        week = add_weeks(start, offset)
        assignment = ensure_assignment(session, week)
        baseline_id = baseline_assignee_member_id(session, week)
        effective_id, override = effective_assignee_member_id(session, week)
        rows.append(
            {
                "week_start": week,
                "baseline_assignee_member_id": baseline_id,
                "effective_assignee_member_id": effective_id,
                "override_type": override.type.value if override else None,
                "status": assignment.status.value,
                "completed_by_member_id": assignment.completed_by_member_id,
                "completion_mode": assignment.completion_mode,
            }
        )

    session.commit()
    return rows


def due_notifications(session: Session, at: datetime) -> list[dict]:
    local_at = at
    week_start = monday_for(local_at.date())
    mark_past_pending_as_missed(session, week_start)

    notifications: list[dict] = []
    minute = local_at.minute

    def assignee_member_for_week(target_week: date) -> tuple[Member | None, CleaningAssignment]:
        assignment = ensure_assignment(session, target_week)
        member = get_member_by_id(session, assignment.assignee_member_id) if assignment.assignee_member_id else None
        return member, assignment

    if local_at.weekday() == 0 and local_at.hour == 11 and minute == 0:
        member, assignment = assignee_member_for_week(week_start)
        warning = ""

        prev_week = add_weeks(week_start, -1)
        _prev_member, prev_assignment = assignee_member_for_week(prev_week)
        if prev_assignment.status != CleaningAssignmentStatus.DONE:
            warning = " Warning: last week is still unconfirmed."

        message = f"It is your turn to clean the common areas this week.{warning}".strip()
        notifications.append(_member_notification(member, "Weekly Cleaning Shift", message))

    if local_at.weekday() == 6 and minute == 0 and local_at.hour in {18, 21}:
        member, assignment = assignee_member_for_week(week_start)
        if assignment.status == CleaningAssignmentStatus.PENDING:
            if local_at.hour == 18:
                message = (
                    "Please mark this week's cleaning as done in Home Assistant after you finish. "
                    "If it is not confirmed, the next person may miss a reminder."
                )
            else:
                message = (
                    "Final reminder: mark this week's cleaning as done in Home Assistant now "
                    "so next week's reminder can be sent correctly."
                )
            notifications.append(_member_notification(member, "Weekly Cleaning Shift", message))

    session.commit()
    return notifications
