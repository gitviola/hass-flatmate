"""Member synchronization and actor resolution helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Member
from ..schemas import MemberSyncItem


def sync_members(session: Session, items: list[MemberSyncItem]) -> list[Member]:
    """Upsert members from Home Assistant mappings."""

    existing = {
        m.ha_user_id: m
        for m in session.execute(select(Member).where(Member.ha_user_id.is_not(None))).scalars().all()
    }

    seen_user_ids: set[str] = set()

    for item in items:
        member = existing.get(item.ha_user_id) if item.ha_user_id else None
        if member is None:
            member = Member(
                display_name=item.display_name.strip(),
                ha_user_id=item.ha_user_id,
                ha_person_entity_id=item.ha_person_entity_id,
                notify_service=item.notify_service,
                active=item.active,
            )
            session.add(member)
        else:
            member.display_name = item.display_name.strip()
            member.ha_person_entity_id = item.ha_person_entity_id
            member.notify_service = item.notify_service
            member.active = item.active

        if item.ha_user_id:
            seen_user_ids.add(item.ha_user_id)

    for member in existing.values():
        if member.ha_user_id and member.ha_user_id not in seen_user_ids:
            member.active = False

    session.commit()

    return session.execute(select(Member).order_by(Member.display_name.asc())).scalars().all()


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
