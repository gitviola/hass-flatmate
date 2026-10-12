"""Member synchronization and actor resolution helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Member
from ..schemas import MemberSyncItem
from .time_utils import now_utc

# Someone re-added within this long after being removed never really moved out
# (e.g. their HA person was edited), so they keep their original move-in.
BRIEF_ABSENCE = timedelta(days=1)


def _as_utc(value: datetime) -> datetime:
    # SQLite drops the offset; stored timestamps are UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _set_active(member: Member, active: bool, now: datetime) -> None:
    """Record move-out on deactivation and a new move-in on a real return."""

    if bool(member.active) == active:
        return
    member.active = active
    if not active:
        if member.moved_out_at is None:
            member.moved_out_at = now
        return
    if member.moved_out_at is not None:
        if now - _as_utc(member.moved_out_at) > BRIEF_ABSENCE:
            member.moved_in_at = now
        member.moved_out_at = None


def sync_members(session: Session, items: list[MemberSyncItem]) -> tuple[list[Member], list[int]]:
    """Upsert members from Home Assistant mappings."""

    existing = {
        m.ha_user_id: m
        for m in session.execute(select(Member).where(Member.ha_user_id.is_not(None))).scalars().all()
    }

    seen_user_ids: set[str] = set()
    deactivated_member_ids: set[int] = set()
    now = now_utc()

    for item in items:
        notify_services = [str(value) for value in item.notify_services if str(value)]
        device_trackers = [str(value) for value in item.device_trackers if str(value)]
        member = existing.get(item.ha_user_id) if item.ha_user_id else None
        if member is None:
            member = Member(
                display_name=item.display_name.strip(),
                ha_user_id=item.ha_user_id,
                ha_person_entity_id=item.ha_person_entity_id,
                notify_service=item.notify_service,
                notify_services=notify_services,
                device_trackers=device_trackers,
                active=item.active,
            )
            session.add(member)
        else:
            was_active = bool(member.active)
            member.display_name = item.display_name.strip()
            member.ha_person_entity_id = item.ha_person_entity_id
            member.notify_service = item.notify_service
            member.notify_services = notify_services
            member.device_trackers = device_trackers
            _set_active(member, item.active, now)
            if was_active and not member.active:
                deactivated_member_ids.add(member.id)

        if item.ha_user_id:
            seen_user_ids.add(item.ha_user_id)

    for member in existing.values():
        if member.ha_user_id and member.ha_user_id not in seen_user_ids:
            if member.active:
                _set_active(member, False, now)
                deactivated_member_ids.add(member.id)

    session.commit()

    rows = session.execute(select(Member).order_by(Member.display_name.asc())).scalars().all()
    return rows, sorted(deactivated_member_ids)


def set_tenancy(session: Session, member: Member, changes: dict[str, datetime | None]) -> Member:
    """Set or clear ``moved_in_at`` / ``moved_out_at``; keys left out stay unchanged."""

    moved_in_at = changes.get("moved_in_at", member.moved_in_at)
    moved_out_at = changes.get("moved_out_at", member.moved_out_at)
    if moved_out_at is not None and member.active:
        raise ValueError("Only a flatmate who is no longer active can have a move-out date")
    if moved_in_at is not None and moved_out_at is not None and _as_utc(moved_out_at) <= _as_utc(moved_in_at):
        raise ValueError("moved_out_at must be after moved_in_at")
    member.moved_in_at = _as_utc(moved_in_at) if moved_in_at is not None else None
    member.moved_out_at = _as_utc(moved_out_at) if moved_out_at is not None else None
    return member


def resolve_actor_member(session: Session, actor_user_id: str | None) -> Member | None:
    """Resolve actor user id to a member; unknown users return None."""

    if not actor_user_id:
        return None
    return session.execute(select(Member).where(Member.ha_user_id == actor_user_id)).scalar_one_or_none()


def get_active_members(session: Session) -> list[Member]:
    return session.execute(
        select(Member).where(Member.active.is_(True)).order_by(Member.display_name.asc())
    ).scalars().all()


def get_member_by_id(session: Session, member_id: int) -> Member | None:
    return session.get(Member, member_id)
