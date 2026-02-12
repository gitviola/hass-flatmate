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


def _linked_manual_swap_return_override(
    session: Session,
    swap_override: CleaningOverride | None,
) -> CleaningOverride | None:
    if swap_override is None:
        return None

    if swap_override.source_event_id is not None:
        linked = session.execute(
            select(CleaningOverride)
            .where(
                CleaningOverride.source_event_id == swap_override.source_event_id,
                CleaningOverride.type == OverrideType.COMPENSATION,
                CleaningOverride.source == OverrideSource.MANUAL,
                CleaningOverride.status == OverrideStatus.PLANNED,
            )
            .order_by(CleaningOverride.created_at.asc())
        ).scalar_one_or_none()
        if linked is not None:
            return linked

    return session.execute(
        select(CleaningOverride)
        .where(
            CleaningOverride.type == OverrideType.COMPENSATION,
            CleaningOverride.source == OverrideSource.MANUAL,
            CleaningOverride.status == OverrideStatus.PLANNED,
            CleaningOverride.member_from_id == swap_override.member_to_id,
            CleaningOverride.member_to_id == swap_override.member_from_id,
            CleaningOverride.week_start > swap_override.week_start,
        )
        .order_by(CleaningOverride.week_start.asc(), CleaningOverride.created_at.asc())
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


def _member_notification(
    member: Member | None,
    title: str,
    message: str,
    *,
    week_start: date | None = None,
    notification_kind: str | None = None,
    notification_slot: str | None = None,
    source_action: str | None = None,
) -> dict:
    payload = {
        "member_id": member.id if member else None,
        "notify_service": member.notify_service if member else None,
        "title": title,
        "message": message,
        "category": "cleaning",
    }
    if week_start is not None:
        payload["week_start"] = week_start
    if notification_kind:
        payload["notification_kind"] = notification_kind
    if notification_slot:
        payload["notification_slot"] = notification_slot
    if source_action:
        payload["source_action"] = source_action
    return payload


def _build_swap_notifications(
    session: Session,
    member_a_id: int,
    member_b_id: int,
    week_start: date,
    *,
    return_week_start: date | None,
    action: str,
    actor_name: str | None = None,
) -> list[dict]:
    member_a = get_member_by_id(session, member_a_id)
    member_b = get_member_by_id(session, member_b_id)
    member_a_name = member_a.display_name if member_a else "member"
    member_b_name = member_b.display_name if member_b else "member"
    original_assignee_id = baseline_assignee_member_id(session, week_start)
    original_assignee = (
        get_member_by_id(session, original_assignee_id)
        if original_assignee_id is not None
        else None
    )
    original_name = original_assignee.display_name if original_assignee is not None else None
    actor_prefix = f"{actor_name} " if actor_name else "A flatmate "
    selected_week_label = week_start.isoformat()
    return_week_label = return_week_start.isoformat() if return_week_start is not None else "the next regular week"

    if action == "created":
        msg_a = (
            f"{actor_prefix}swapped shifts between week {selected_week_label} and week {return_week_label} with "
            f"{member_b_name}. {member_b_name} is assigned for {selected_week_label}, and you are assigned for {return_week_label}."
        )
        msg_b = (
            f"{actor_prefix}swapped shifts between week {selected_week_label} and week {return_week_label} with "
            f"{member_a_name}. You are assigned for {selected_week_label}, and {member_a_name} is assigned for {return_week_label}."
        )
    elif action == "updated":
        msg_a = (
            f"{actor_prefix}updated the shift swap: {member_b_name} now covers week {selected_week_label}, "
            f"and you cover week {return_week_label}."
        )
        msg_b = (
            f"{actor_prefix}updated the shift swap: you now cover week {selected_week_label}, "
            f"and {member_a_name} covers week {return_week_label}."
        )
    else:
        msg_a = (
            f"{actor_prefix}canceled the shift swap between week {selected_week_label} and week {return_week_label}. "
            "Everyone is back on their regular schedule."
        )
        msg_b = (
            f"{actor_prefix}canceled the shift swap between week {selected_week_label} and week {return_week_label}. "
            "Everyone is back on their regular schedule."
        )

    if original_name:
        msg_a = f"{msg_a} Original assignee for {selected_week_label}: {original_name}."
        msg_b = f"{msg_b} Original assignee for {selected_week_label}: {original_name}."

    title = "Weekly Cleaning Shift"
    return [
        _member_notification(
            member_a,
            title,
            msg_a,
            week_start=week_start,
            notification_kind="swap_notice",
            source_action=f"cleaning_swap_{action}",
        ),
        _member_notification(
            member_b,
            title,
            msg_b,
            week_start=week_start,
            notification_kind="swap_notice",
            source_action=f"cleaning_swap_{action}",
        ),
    ]


def _require_active_member(session: Session, member_id: int, *, field_name: str) -> Member:
    member = get_member_by_id(session, member_id)
    if member is None:
        raise ValueError(f"{field_name} not found")
    if not member.active:
        raise ValueError(f"{field_name} is inactive")
    return member


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
    existing_return_override = _linked_manual_swap_return_override(session, existing)

    notifications: list[dict] = []
    action = "created"

    if cancel:
        if existing is not None:
            return_week_start = existing_return_override.week_start if existing_return_override else None

            _cancel_override_without_status_collision(
                session,
                override=existing,
                actor_member_id=actor_member.id if actor_member else None,
            )
            if existing_return_override is not None:
                _cancel_override_without_status_collision(
                    session,
                    override=existing_return_override,
                    actor_member_id=actor_member.id if actor_member else None,
                )

            action = "canceled"
            notifications = _build_swap_notifications(
                session,
                existing.member_from_id,
                existing.member_to_id,
                week_start,
                return_week_start=return_week_start,
                action="canceled",
                actor_name=actor_member.display_name if actor_member else None,
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
                    "return_week_start": return_week_start.isoformat() if return_week_start else None,
                },
            )
        session.flush()
        ensure_assignment(session, week_start)
        if existing_return_override is not None:
            ensure_assignment(session, existing_return_override.week_start)
        session.commit()
        return None, notifications

    _require_active_member(session, member_a_id, field_name="member_a_id")
    _require_active_member(session, member_b_id, field_name="member_b_id")

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
        session.flush()
        action = "created"
    else:
        old_member_to_id = existing.member_to_id
        existing.member_from_id = member_a_id
        existing.member_to_id = member_b_id
        action = "updated"

    ignore_override_ids = {existing.id}
    if existing_return_override is not None:
        ignore_override_ids.add(existing_return_override.id)

    return_week_start = _next_baseline_week_for_member(
        session,
        member_b_id,
        start_week=add_weeks(week_start, 1),
        ignore_override_ids=ignore_override_ids,
    )

    swap_event = log_event(
        session,
        domain="cleaning",
        action=f"cleaning_swap_{action}",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={
            "week_start": week_start.isoformat(),
            "member_a_id": member_a_id,
            "member_b_id": member_b_id,
            "return_week_start": return_week_start.isoformat(),
        },
    )

    existing.source_event_id = swap_event.id

    if existing_return_override is None:
        existing_return_override = CleaningOverride(
            week_start=return_week_start,
            type=OverrideType.COMPENSATION,
            source=OverrideSource.MANUAL,
            source_event_id=swap_event.id,
            member_from_id=member_b_id,
            member_to_id=member_a_id,
            status=OverrideStatus.PLANNED,
            created_by_member_id=actor_member.id if actor_member else None,
        )
        session.add(existing_return_override)
    else:
        existing_return_override.week_start = return_week_start
        existing_return_override.type = OverrideType.COMPENSATION
        existing_return_override.source = OverrideSource.MANUAL
        existing_return_override.source_event_id = swap_event.id
        existing_return_override.member_from_id = member_b_id
        existing_return_override.member_to_id = member_a_id
        existing_return_override.status = OverrideStatus.PLANNED
        existing_return_override.created_by_member_id = actor_member.id if actor_member else None

    notifications = _build_swap_notifications(
        session,
        member_a_id,
        member_b_id,
        week_start,
        return_week_start=return_week_start,
        action=action,
        actor_name=actor_member.display_name if actor_member else None,
    )

    # Notify old partner if they were replaced in a swap edit
    if action == "updated" and old_member_to_id != member_b_id:
        old_partner = get_member_by_id(session, old_member_to_id)
        if old_partner is not None:
            actor_prefix = f"{actor_member.display_name} " if actor_member else "A flatmate "
            new_partner = get_member_by_id(session, member_b_id)
            new_partner_name = new_partner.display_name if new_partner else "another flatmate"
            notifications.append(
                _member_notification(
                    old_partner,
                    "Weekly Cleaning Shift",
                    f"{actor_prefix}changed the swap for week {week_start.isoformat()}. "
                    f"{new_partner_name} is now swapped in instead of you. Your original schedule is restored.",
                    week_start=week_start,
                    notification_kind="swap_notice",
                    source_action="cleaning_swap_updated",
                )
            )

    ensure_assignment(session, week_start)
    ensure_assignment(session, return_week_start)

    session.commit()
    return existing, notifications


def _next_baseline_week_for_member(
    session: Session,
    member_id: int,
    *,
    start_week: date,
    ignore_override_ids: set[int] | None = None,
    max_scan_weeks: int = 156,
) -> date:
    ignore_ids = ignore_override_ids or set()
    candidate = start_week
    for _ in range(max_scan_weeks):
        baseline_id = baseline_assignee_member_id(session, candidate)
        override = _planned_override_for_week(session, candidate)
        if override is not None and override.id in ignore_ids:
            override = None
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
                week_start=week_start,
                notification_kind="completion_confirmation",
                source_action="cleaning_done",
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
) -> list[dict]:
    _ensure_week_start_is_monday(week_start)
    actor_member = resolve_actor_member(session, actor_user_id)
    assignment = ensure_assignment(session, week_start)

    if assignment.status != CleaningAssignmentStatus.DONE:
        return []

    previous_completed_by_id = assignment.completed_by_member_id
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

    canceled_compensation_members: list[tuple[int, int, date]] = []
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
                canceled_compensation_members.append(
                    (compensation.member_from_id, compensation.member_to_id, compensation.week_start)
                )
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

    # Build notifications
    notifications: list[dict] = []
    actor_prefix = f"{actor_member.display_name} " if actor_member else "A flatmate "
    title = "Weekly Cleaning Shift"
    week_label = week_start.isoformat()

    # Notify the effective assignee that their week was reopened
    effective_id, _ = effective_assignee_member_id(session, week_start)
    assignee = get_member_by_id(session, effective_id) if effective_id else None
    if assignee is not None:
        notifications.append(
            _member_notification(
                assignee,
                title,
                f"{actor_prefix}marked the cleaning shift for week {week_label} as not done yet.",
                week_start=week_start,
                notification_kind="undo_notice",
                source_action="cleaning_undone",
            )
        )

    # If a different person had completed it (swap/takeover), notify them too
    if (
        previous_completed_by_id is not None
        and effective_id is not None
        and previous_completed_by_id != effective_id
    ):
        completer = get_member_by_id(session, previous_completed_by_id)
        if completer is not None:
            notifications.append(
                _member_notification(
                    completer,
                    title,
                    f"{actor_prefix}undid the completion for week {week_label}. The shift still needs to be done.",
                    week_start=week_start,
                    notification_kind="undo_notice",
                    source_action="cleaning_undone",
                )
            )

    # If takeover compensation was canceled, notify both parties
    for from_id, to_id, comp_week in canceled_compensation_members:
        from_member = get_member_by_id(session, from_id)
        to_member = get_member_by_id(session, to_id)
        comp_label = comp_week.isoformat()
        if from_member is not None:
            notifications.append(
                _member_notification(
                    from_member,
                    title,
                    f"{actor_prefix}undid the takeover for week {week_label}. "
                    f"Your return shift for week {comp_label} is no longer needed.",
                    week_start=comp_week,
                    notification_kind="undo_notice",
                    source_action="cleaning_undone",
                )
            )
        if to_member is not None:
            notifications.append(
                _member_notification(
                    to_member,
                    title,
                    f"{actor_prefix}undid the takeover for week {week_label}. "
                    f"The return shift for week {comp_label} is no longer needed — your regular shift is back.",
                    week_start=comp_week,
                    notification_kind="undo_notice",
                    source_action="cleaning_undone",
                )
            )

    return notifications


def _build_compensation_notifications(
    session: Session,
    *,
    week_start: date,
    source_week_start: date | None,
    member_from_id: int,
    member_to_id: int,
    actor_name: str | None = None,
) -> list[dict]:
    member_from = get_member_by_id(session, member_from_id)
    member_to = get_member_by_id(session, member_to_id)
    member_to_name = member_to.display_name if member_to else "another member"
    actor_prefix = f"{actor_name} recorded that " if actor_name else "A flatmate recorded that "
    source_label = source_week_start.isoformat() if source_week_start is not None else "this week"
    make_up_label = week_start.isoformat()

    title = "Weekly Cleaning Shift"
    msg_from = (
        f"{actor_prefix}{member_to_name} took over your shift in week {source_label}. "
        f"Your return shift is planned for week {make_up_label}."
    )
    msg_to = (
        f"{actor_prefix}you took over {member_to_name}'s shift in week {source_label}. "
        f"{member_to_name} is assigned to your regular week {make_up_label} as a return shift."
    )
    return [
        _member_notification(
            member_from,
            title,
            msg_from,
            week_start=week_start,
            notification_kind="takeover_compensation_notice",
            source_action="cleaning_takeover_done",
        ),
        _member_notification(
            member_to,
            title,
            msg_to,
            week_start=week_start,
            notification_kind="takeover_compensation_notice",
            source_action="cleaning_takeover_done",
        ),
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
            f"A planned cleaning return shift for week {override.week_start.isoformat()} was canceled because "
            f"{inactive_label} is no longer active in the flat."
        )

    notifications: list[dict] = []
    for member_id in sorted({override.member_from_id, override.member_to_id} - inactive_member_ids):
        member = get_member_by_id(session, member_id)
        if member is None or not member.active:
            continue
        notifications.append(
            _member_notification(
                member,
                "Weekly Cleaning Shift",
                message,
                week_start=override.week_start,
                notification_kind="override_canceled_notice",
                source_action="cleaning_override_auto_canceled_member_inactive",
            )
        )

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
        source_week_start=week_start,
        member_from_id=cleaner_member_id,
        member_to_id=original_assignee_member_id,
        actor_name=actor_member.display_name if actor_member else None,
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


def _parse_source_week_start(payload: dict | None) -> date | None:
    if not isinstance(payload, dict):
        return None

    source_value = payload.get("source_week_start") or payload.get("week_start")
    if isinstance(source_value, date):
        return source_value
    if not isinstance(source_value, str):
        return None

    normalized = source_value.strip()
    if not normalized:
        return None
    normalized = normalized.split("T", maxsplit=1)[0].split(" ", maxsplit=1)[0]
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None


def get_schedule(session: Session, *, weeks_ahead: int, from_week_start: date | None = None) -> list[dict]:
    start = from_week_start or week_start_for(now_utc())
    rows: list[dict] = []
    source_week_by_event_id: dict[int, date | None] = {}

    for offset in range(max(weeks_ahead, 0)):
        week = add_weeks(start, offset)
        assignment = ensure_assignment(session, week)
        baseline_id = baseline_assignee_member_id(session, week)
        effective_id, override = effective_assignee_member_id(session, week)
        source_week_start = None
        if override is not None and override.source_event_id is not None:
            event_id = int(override.source_event_id)
            if event_id not in source_week_by_event_id:
                event = session.get(ActivityEvent, event_id)
                source_week_by_event_id[event_id] = _parse_source_week_start(
                    event.payload_json if event is not None else None
                )
            source_week_start = source_week_by_event_id.get(event_id)
        rows.append(
            {
                "week_start": week,
                "baseline_assignee_member_id": baseline_id,
                "effective_assignee_member_id": effective_id,
                "override_type": override.type.value if override else None,
                "override_source": override.source.value if override else None,
                "source_week_start": source_week_start,
                "status": assignment.status.value,
                "completed_by_member_id": assignment.completed_by_member_id,
                "completion_mode": assignment.completion_mode,
                "completed_at": assignment.completed_at,
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
        notifications.append(
            _member_notification(
                member,
                "Weekly Cleaning Shift",
                message,
                week_start=week_start,
                notification_kind="weekly_assignment",
                notification_slot="monday_11",
                source_action="cleaning_notifications_due",
            )
        )

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
            notifications.append(
                _member_notification(
                    member,
                    "Weekly Cleaning Shift",
                    message,
                    week_start=week_start,
                    notification_kind="weekly_reminder",
                    notification_slot=f"sunday_{local_at.hour}",
                    source_action="cleaning_notifications_due",
                )
            )

    session.commit()
    return notifications


def record_notification_dispatches(session: Session, *, records: list[dict]) -> int:
    if not records:
        return 0

    allowed_statuses = {
        "sent",
        "failed",
        "skipped",
        "suppressed",
        "test_redirected",
    }
    inserted = 0

    for record in records:
        if not isinstance(record, dict):
            continue

        week_start_raw = record.get("week_start")
        if not isinstance(week_start_raw, date):
            raise ValueError("week_start is required for cleaning notification dispatch records")
        _ensure_week_start_is_monday(week_start_raw)

        status_raw = str(record.get("status") or "").strip().lower()
        if status_raw not in allowed_statuses:
            raise ValueError(
                "status must be one of: sent, failed, skipped, suppressed, test_redirected"
            )

        member_id_raw = record.get("member_id")
        member_id = None
        if member_id_raw is not None:
            try:
                member_id = int(member_id_raw)
            except (TypeError, ValueError):
                member_id = None

        dispatched_at = record.get("dispatched_at")
        created_at = dispatched_at if isinstance(dispatched_at, datetime) else None

        log_event(
            session,
            domain="cleaning",
            action="cleaning_notification_dispatch",
            actor_member_id=None,
            actor_user_id_raw=None,
            payload={
                "week_start": week_start_raw.isoformat(),
                "member_id": member_id,
                "notify_service": str(record.get("notify_service") or "") or None,
                "title": str(record.get("title") or "") or None,
                "message": str(record.get("message") or "") or None,
                "notification_kind": str(record.get("notification_kind") or "") or None,
                "notification_slot": str(record.get("notification_slot") or "") or None,
                "source_action": str(record.get("source_action") or "") or None,
                "status": status_raw,
                "reason": str(record.get("reason") or "") or None,
            },
            created_at=created_at,
        )
        inserted += 1

    session.commit()
    return inserted
