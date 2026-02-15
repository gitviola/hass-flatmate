"""SQLAlchemy models for flatmate service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ShoppingStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    DELETED = "deleted"


class CleaningAssignmentStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    MISSED = "missed"


class OverrideType(str, Enum):
    MANUAL_SWAP = "manual_swap"
    COMPENSATION = "compensation"


class OverrideSource(str, Enum):
    MANUAL = "manual"
    TAKEOVER_COMPLETION = "takeover_completion"


class OverrideStatus(str, Enum):
    PLANNED = "planned"
    APPLIED = "applied"
    CANCELED = "canceled"


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    ha_user_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    ha_person_entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notify_service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ShoppingStatus] = mapped_column(SAEnum(ShoppingStatus), default=ShoppingStatus.OPEN, nullable=False)

    added_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    added_by_user_id_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    completed_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    completed_by_user_id_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deleted_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    deleted_by_user_id_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ShoppingFavorite(Base):
    __tablename__ = "shopping_favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    created_by_user_id_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    actor_user_id_raw: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class RotationConfig(Base):
    __tablename__ = "rotation_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False, default=1)
    ordered_member_ids_json: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    anchor_week_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CleaningAssignment(Base):
    __tablename__ = "cleaning_assignments"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    assignee_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    status: Mapped[CleaningAssignmentStatus] = mapped_column(
        SAEnum(CleaningAssignmentStatus),
        default=CleaningAssignmentStatus.PENDING,
        nullable=False,
    )
    completed_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    completion_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notified_slots: Mapped[dict | None] = mapped_column(JSON, default=dict, nullable=True)


class CleaningOverride(Base):
    __tablename__ = "cleaning_overrides"
    __table_args__ = (
        UniqueConstraint("week_start", "status", name="uq_override_week_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    type: Mapped[OverrideType] = mapped_column(SAEnum(OverrideType), nullable=False)
    source: Mapped[OverrideSource] = mapped_column(SAEnum(OverrideSource), nullable=False)
    source_event_id: Mapped[int | None] = mapped_column(ForeignKey("activity_events.id"), nullable=True)

    member_from_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)
    member_to_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False)

    status: Mapped[OverrideStatus] = mapped_column(SAEnum(OverrideStatus), default=OverrideStatus.PLANNED, nullable=False)
    created_by_member_id: Mapped[int | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
