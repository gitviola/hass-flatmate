"""Shopping list domain logic and fairness statistics."""

from __future__ import annotations

import hashlib
import html
from datetime import timedelta

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from ..models import Member, ShoppingFavorite, ShoppingItem, ShoppingStatus
from ..services.activity import log_event
from ..services.members import get_active_members, resolve_actor_member
from ..services.time_utils import now_utc


def list_items(session: Session) -> list[ShoppingItem]:
    return session.execute(
        select(ShoppingItem).order_by(
            case((ShoppingItem.status == ShoppingStatus.OPEN, 0), else_=1),
            ShoppingItem.added_at.desc(),
        )
    ).scalars().all()


def add_item(session: Session, name: str, actor_user_id: str | None) -> ShoppingItem:
    actor_member = resolve_actor_member(session, actor_user_id)

    item = ShoppingItem(
        name=name.strip(),
        status=ShoppingStatus.OPEN,
        added_by_member_id=actor_member.id if actor_member else None,
        added_by_user_id_raw=actor_user_id,
    )
    session.add(item)
    session.flush()

    log_event(
        session,
        domain="shopping",
        action="shopping_item_added",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={"item_id": item.id, "name": item.name},
    )
    session.commit()
    return item


def complete_item(session: Session, item_id: int, actor_user_id: str | None) -> ShoppingItem:
    item = session.get(ShoppingItem, item_id)
    if item is None:
        raise ValueError("Shopping item not found")
    if item.status != ShoppingStatus.OPEN:
        raise ValueError("Only open items can be completed")

    actor_member = resolve_actor_member(session, actor_user_id)
    now = now_utc()

    item.status = ShoppingStatus.COMPLETED
    item.completed_by_member_id = actor_member.id if actor_member else None
    item.completed_by_user_id_raw = actor_user_id
    item.completed_at = now

    log_event(
        session,
        domain="shopping",
        action="shopping_item_completed",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={"item_id": item.id, "name": item.name},
        created_at=now,
    )
    session.commit()
    return item


def delete_item(session: Session, item_id: int, actor_user_id: str | None) -> ShoppingItem:
    item = session.get(ShoppingItem, item_id)
    if item is None:
        raise ValueError("Shopping item not found")
    if item.status != ShoppingStatus.OPEN:
        raise ValueError("Only open items can be deleted")

    actor_member = resolve_actor_member(session, actor_user_id)
    now = now_utc()

    item.status = ShoppingStatus.DELETED
    item.deleted_by_member_id = actor_member.id if actor_member else None
    item.deleted_by_user_id_raw = actor_user_id
    item.deleted_at = now

    log_event(
        session,
        domain="shopping",
        action="shopping_item_deleted",
        actor_member_id=actor_member.id if actor_member else None,
        actor_user_id_raw=actor_user_id,
        payload={"item_id": item.id, "name": item.name},
        created_at=now,
    )
    session.commit()
    return item


def add_favorite(session: Session, name: str, actor_user_id: str | None) -> ShoppingFavorite:
    actor_member = resolve_actor_member(session, actor_user_id)

    favorite = session.execute(
        select(ShoppingFavorite).where(
            func.lower(ShoppingFavorite.name) == name.strip().lower(),
            ShoppingFavorite.active.is_(True),
        )
    ).scalar_one_or_none()
    if favorite is not None:
        return favorite

    favorite = ShoppingFavorite(
        name=name.strip(),
        created_by_member_id=actor_member.id if actor_member else None,
        created_by_user_id_raw=actor_user_id,
        active=True,
    )
    session.add(favorite)
    session.commit()
    return favorite


def delete_favorite(session: Session, favorite_id: int, actor_user_id: str | None) -> None:
    del actor_user_id
    favorite = session.get(ShoppingFavorite, favorite_id)
    if favorite is None:
        raise ValueError("Favorite not found")
    favorite.active = False
    session.commit()


def list_favorites(session: Session) -> list[ShoppingFavorite]:
    return session.execute(
        select(ShoppingFavorite)
        .where(ShoppingFavorite.active.is_(True))
        .order_by(ShoppingFavorite.name.asc())
    ).scalars().all()


def recent_item_names(session: Session, limit: int = 20) -> list[str]:
    rows = session.execute(
        select(ShoppingItem).order_by(
            desc(
                func.coalesce(
                    ShoppingItem.completed_at,
                    ShoppingItem.deleted_at,
                    ShoppingItem.added_at,
                )
            )
        )
    ).scalars().all()

    seen: set[str] = set()
    recents: list[str] = []
    for row in rows:
        key = row.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        recents.append(row.name)
        if len(recents) >= limit:
            break
    return recents


def buy_distribution(session: Session, window_days: int = 90) -> dict:
    cutoff = now_utc() - timedelta(days=window_days)

    active_members = get_active_members(session)

    counts_by_member = {member.id: 0 for member in active_members}

    completed_rows = session.execute(
        select(ShoppingItem.completed_by_member_id)
        .where(
            ShoppingItem.status == ShoppingStatus.COMPLETED,
            ShoppingItem.completed_at.is_not(None),
            ShoppingItem.completed_at >= cutoff,
        )
    ).all()

    total_completed = len(completed_rows)
    unknown_excluded_count = 0
    for (member_id,) in completed_rows:
        if member_id is None:
            unknown_excluded_count += 1
            continue
        if member_id in counts_by_member:
            counts_by_member[member_id] += 1

    valid_total = sum(counts_by_member.values())

    distribution = [
        {
            "member_id": member.id,
            "name": member.display_name,
            "count": counts_by_member[member.id],
            "percent": (counts_by_member[member.id] / valid_total * 100.0) if valid_total else 0.0,
        }
        for member in active_members
    ]

    distribution.sort(key=lambda x: (-x["count"], x["name"].lower()))

    svg_render_version = hashlib.sha1(
        str([(row["member_id"], row["count"]) for row in distribution]).encode("utf-8")
    ).hexdigest()[:12]

    return {
        "window_days": window_days,
        "total_completed": total_completed,
        "unknown_excluded_count": unknown_excluded_count,
        "distribution": distribution,
        "svg_render_version": svg_render_version,
    }


def distribution_svg(stats: dict) -> str:
    rows = stats["distribution"]
    width = 820
    height = 120
    outer_x = 8
    outer_y = 12
    outer_w = width - 16
    outer_h = 84

    palette = [
        "#e3eefc",
        "#dcefdc",
        "#f7ead4",
        "#f5dddf",
        "#e8e1f6",
        "#d8edf1",
        "#f0f0f0",
    ]

    total = sum(int(row["count"]) for row in rows)
    has_total = total > 0
    base_width = outer_w / max(len(rows), 1)

    segments: list[str] = []
    x = outer_x
    for idx, row in enumerate(rows):
        if has_total:
            raw_width = outer_w * (float(row["count"]) / total)
            seg_w = max(raw_width, 90.0)
        else:
            seg_w = max(base_width, 90.0)

        if idx == len(rows) - 1:
            seg_w = (outer_x + outer_w) - x

        fill = palette[idx % len(palette)]
        name = html.escape(str(row["name"]))
        count = int(row["count"])
        text_x = x + (seg_w / 2)

        segments.append(
            (
                f'<rect x="{x:.2f}" y="{outer_y}" width="{seg_w:.2f}" height="{outer_h}" '
                f'fill="{fill}" stroke="#111" stroke-width="1" />'
                f'<text x="{text_x:.2f}" y="47" text-anchor="middle" '
                f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="22" '
                f'fill="#111">{name}</text>'
                f'<text x="{text_x:.2f}" y="74" text-anchor="middle" '
                f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="18" '
                f'fill="#111">{count}</text>'
            )
        )
        x += seg_w

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="Shopping distribution">'
        f'<rect x="{outer_x}" y="{outer_y}" width="{outer_w}" height="{outer_h}" '
        f'fill="#fff" stroke="#111" stroke-width="2" rx="8" ry="8" />'
        f"{''.join(segments)}"
        "</svg>"
    )
    return svg
