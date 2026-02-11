"""Activity event persistence and retrieval."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ActivityEvent


def log_event(
    session: Session,
    *,
    domain: str,
    action: str,
    actor_member_id: int | None,
    actor_user_id_raw: str | None,
    payload: dict,
    created_at: datetime | None = None,
) -> ActivityEvent:
    event = ActivityEvent(
        domain=domain,
        action=action,
        actor_member_id=actor_member_id,
        actor_user_id_raw=actor_user_id_raw,
        payload_json=payload,
    )
    if created_at is not None:
        event.created_at = created_at
    session.add(event)
    session.flush()
    return event


def list_events(session: Session, limit: int = 50) -> list[ActivityEvent]:
    return session.execute(
        select(ActivityEvent).order_by(ActivityEvent.created_at.desc()).limit(limit)
    ).scalars().all()
