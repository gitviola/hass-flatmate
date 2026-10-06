"""Shopping list domain logic and fairness statistics."""

from __future__ import annotations

import hashlib
import html
from datetime import datetime, timedelta, timezone

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
    if item.status == ShoppingStatus.COMPLETED:
        return item
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
    if item.status == ShoppingStatus.DELETED:
        return item
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
    if limit <= 0:
        return []

    def _normalize(value: str) -> str:
        return value.strip().lower()

    open_names = {
        _normalize(name)
        for (name,) in session.execute(
            select(ShoppingItem.name).where(ShoppingItem.status == ShoppingStatus.OPEN)
        ).all()
        if isinstance(name, str) and _normalize(name)
    }

    completed_rows = session.execute(
        select(ShoppingItem.name, ShoppingItem.completed_at)
        .where(
            ShoppingItem.status == ShoppingStatus.COMPLETED,
            ShoppingItem.completed_at.is_not(None),
        )
        .order_by(ShoppingItem.completed_at.desc(), ShoppingItem.id.desc())
    ).all()

    favorite_rows = session.execute(
        select(ShoppingFavorite.name, ShoppingFavorite.created_at)
        .where(ShoppingFavorite.active.is_(True))
        .order_by(ShoppingFavorite.created_at.desc(), ShoppingFavorite.id.desc())
    ).all()

    candidates: dict[str, dict] = {}

    for name, completed_at in completed_rows:
        if not isinstance(name, str):
            continue
        key = _normalize(name)
        if not key:
            continue
        entry = candidates.setdefault(
            key,
            {
                "name": name.strip(),
                "buy_count": 0,
                "last_completed_at": None,
                "last_favorited_at": None,
            },
        )
        entry["buy_count"] += 1
        if entry["last_completed_at"] is None or (
            isinstance(completed_at, datetime) and completed_at > entry["last_completed_at"]
        ):
            entry["last_completed_at"] = completed_at
            entry["name"] = name.strip()

    for name, created_at in favorite_rows:
        if not isinstance(name, str):
            continue
        key = _normalize(name)
        if not key:
            continue
        entry = candidates.setdefault(
            key,
            {
                "name": name.strip(),
                "buy_count": 0,
                "last_completed_at": None,
                "last_favorited_at": None,
            },
        )
        if entry["buy_count"] == 0:
            entry["name"] = name.strip()
        if entry["last_favorited_at"] is None or (
            isinstance(created_at, datetime) and created_at > entry["last_favorited_at"]
        ):
            entry["last_favorited_at"] = created_at

    def _epoch_or_floor(value: datetime | None) -> float:
        if not isinstance(value, datetime):
            return float("-inf")
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    ranked = [
        entry
        for key, entry in candidates.items()
        if key not in open_names and (entry["buy_count"] > 0 or entry["last_favorited_at"] is not None)
    ]
    ranked.sort(
        key=lambda entry: (
            -int(entry["buy_count"]),
            -max(
                _epoch_or_floor(entry["last_completed_at"]),
                _epoch_or_floor(entry["last_favorited_at"]),
            ),
            str(entry["name"]).lower(),
        )
    )

    return [str(entry["name"]) for entry in ranked[:limit]]


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

    # All-time, so a tie can still be broken by purchases older than the window.
    last_purchase_by_member = dict(
        session.execute(
            select(ShoppingItem.completed_by_member_id, func.max(ShoppingItem.completed_at))
            .where(
                ShoppingItem.status == ShoppingStatus.COMPLETED,
                ShoppingItem.completed_by_member_id.is_not(None),
            )
            .group_by(ShoppingItem.completed_by_member_id)
        ).all()
    )
    first_member_created_at = session.execute(select(func.min(Member.created_at))).scalar_one_or_none()

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

    recommendation = buy_order(
        active_members,
        counts_by_member,
        last_purchase_by_member,
        first_member_created_at=first_member_created_at,
        window_days=window_days,
    )
    # Most purchases first; on equal counts the more pressing buyer goes lower, next to the recommendation.
    rank_by_member = {row["member_id"]: row["rank"] for row in recommendation["buy_order"]}
    distribution.sort(key=lambda x: (-x["count"], -rank_by_member.get(x["member_id"], 0), x["name"].lower()))

    svg_render_version = hashlib.sha1(
        str([(row["member_id"], row["count"]) for row in distribution]).encode("utf-8")
    ).hexdigest()[:12]

    return {
        "window_days": window_days,
        "total_completed": total_completed,
        "unknown_excluded_count": unknown_excluded_count,
        "distribution": distribution,
        "svg_render_version": svg_render_version,
        **recommendation,
    }


# Members created this close to the very first one came from the initial sync,
# so their created_at is the install date, not the day they moved in.
FOUNDING_MEMBER_GRACE = timedelta(days=1)


def moved_in_at(member: Member, first_member_created_at: datetime | None) -> datetime | None:
    """When the member joined the flat, or None for members from the initial sync."""

    created_at = as_utc(member.created_at)
    if first_member_created_at is None or created_at <= as_utc(first_member_created_at) + FOUNDING_MEMBER_GRACE:
        return None
    return created_at


def _calendar_days_since(value: datetime, now: datetime) -> int:
    # Calendar days, so someone who moved in on the 1st "moved in 5 days ago" on the 6th.
    return (now.date() - value.date()).days


def _days_ago(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days >= 14:
        return f"{days // 7} weeks ago"
    return f"{days} days ago"


def _join_names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def buy_order(
    members: list[Member],
    counts_by_member: dict[int, int],
    last_purchase_by_member: dict[int, datetime],
    *,
    first_member_created_at: datetime | None,
    window_days: int,
) -> list[dict]:
    """Rank active members by who should buy next.

    The purchases in the window are split into fair shares by how many of the
    window's days each member lived in the flat, so someone who just moved in
    isn't pushed to the front for having bought nothing yet. Whoever is furthest
    below their fair share goes first; on a tie, whoever bought least recently.

    Returns ``buy_order`` plus ``buy_order_note``: one short line explaining the
    recommended pair when it would otherwise look unfair, else empty.
    """

    now = now_utc()
    total = sum(counts_by_member.get(member.id, 0) for member in members)

    rows = []
    for member in members:
        joined = moved_in_at(member, first_member_created_at)
        if joined is None:
            days_present = float(window_days)
        else:
            days_present = min(max((now - joined).total_seconds() / 86400, 0.0), float(window_days))
        last_purchase = last_purchase_by_member.get(member.id)
        rows.append(
            {
                "member": member,
                "count": counts_by_member.get(member.id, 0),
                "joined": joined,
                "days_present": days_present,
                "last_purchase": as_utc(last_purchase) if last_purchase is not None else None,
            }
        )

    present_total = sum(row["days_present"] for row in rows)
    for row in rows:
        row["fair_share"] = total * row["days_present"] / present_total if present_total else 0.0
        # Rounded so float noise can't split a real tie.
        row["balance"] = round(row["count"] - row["fair_share"], 6)

    def _sort_key(row: dict) -> tuple:
        reference = row["last_purchase"] or row["joined"]
        return (
            row["balance"],
            reference.timestamp() if reference is not None else float("-inf"),
            row["member"].display_name.lower(),
        )

    rows.sort(key=_sort_key)

    order = []
    for index, row in enumerate(rows):
        member = row["member"]
        is_new = row["joined"] is not None and row["days_present"] < window_days
        days_since_joined = _calendar_days_since(row["joined"], now) if row["joined"] else None

        if row["balance"] < -0.05:
            standing = f"{-row['balance']:.1f} behind"
        elif row["balance"] > 0.05:
            standing = f"{row['balance']:.1f} ahead"
        else:
            standing = "even"
        reason = f"{row['count']} bought in {window_days} days, fair share {row['fair_share']:.1f}, {standing}"
        if is_new:
            reason = f"Moved in {_days_ago(days_since_joined)}: {reason}"

        order.append(
            {
                "rank": index + 1,
                "member_id": member.id,
                "name": member.display_name,
                "person_entity_id": member.ha_person_entity_id,
                "count": row["count"],
                "fair_share": round(row["fair_share"], 2),
                "balance": round(row["balance"], 2),
                "days_present": round(row["days_present"]),
                "moved_in_at": row["joined"],
                "new_member": is_new,
                "last_purchase_at": row["last_purchase"],
                "reason": reason,
            }
        )

    return {"buy_order": order, "buy_order_note": _recommendation_note(rows, now)}


RECOMMENDED_COUNT = 2


def _recommendation_note(rows: list[dict], now: datetime) -> str:
    """Explain the recommended pair where people would ask "why me?"."""

    recommended = rows[:RECOMMENDED_COUNT]
    # Newcomers ranked after a recommended member who bought more than them.
    newcomers = [
        other
        for index, other in enumerate(rows)
        if other["joined"] is not None
        and any(row["count"] > other["count"] for row in recommended[:index])
    ]
    notes = []
    if len(newcomers) == 1:
        days = _calendar_days_since(newcomers[0]["joined"], now)
        notes.append(f"{newcomers[0]['member'].display_name} only moved in {_days_ago(days)}.")
    elif newcomers:
        notes.append(f"{_join_names([row['member'].display_name for row in newcomers])} only moved in recently.")

    # A tie that decides who is recommended, or in which order, named so it reads under the chart.
    for index in range(min(RECOMMENDED_COUNT, len(rows) - 1)):
        if rows[index]["balance"] != rows[index + 1]["balance"]:
            continue
        tied = [rows[index]]
        for other in rows[index + 1 :]:
            if other["balance"] != rows[index]["balance"]:
                break
            tied.append(other)
        names = [row["member"].display_name for row in tied]
        if len(tied) == 2 and all(row["last_purchase"] is not None for row in tied):
            notes.append(f"{names[0]}'s last purchase was longer ago than {names[1]}'s.")
        else:
            notes.append(f"{_join_names(names)} have the same amount, so whoever bought longest ago goes first.")
        break
    return " ".join(notes)


def as_utc(value: datetime) -> datetime:
    # SQLite drops the offset; stored timestamps are UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def member_purchase_history(session: Session, member_id: int, window_days: int = 90) -> dict:
    """All purchases completed by a member, newest first.

    ``in_window`` uses the same rolling cutoff as ``buy_distribution`` so the
    flagged purchases add up to the member's distribution count.
    """

    member = session.get(Member, member_id)
    if member is None:
        raise LookupError("Member not found")

    cutoff = now_utc() - timedelta(days=window_days)
    rows = session.execute(
        select(ShoppingItem)
        .where(
            ShoppingItem.completed_by_member_id == member_id,
            ShoppingItem.status == ShoppingStatus.COMPLETED,
            ShoppingItem.completed_at.is_not(None),
        )
        .order_by(ShoppingItem.completed_at.desc(), ShoppingItem.id.desc())
    ).scalars().all()

    purchases = []
    for row in rows:
        completed_at = as_utc(row.completed_at)
        purchases.append(
            {
                "id": row.id,
                "name": row.name,
                "completed_at": completed_at,
                "in_window": completed_at >= cutoff,
            }
        )

    return {
        "member_id": member.id,
        "display_name": member.display_name,
        "window_days": window_days,
        "window_start": cutoff,
        "total_count": len(purchases),
        "in_window_count": sum(1 for p in purchases if p["in_window"]),
        "purchases": purchases,
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
    member_count = max(len(rows), 1)
    min_segment_width = min(90.0, outer_w / member_count)
    remaining_width = max(outer_w - (min_segment_width * member_count), 0.0)

    segments: list[str] = []
    x = outer_x
    for idx, row in enumerate(rows):
        if total > 0:
            seg_w = min_segment_width + (remaining_width * (float(row["count"]) / total))
        else:
            seg_w = outer_w / member_count

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
