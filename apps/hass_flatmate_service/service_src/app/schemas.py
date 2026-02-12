"""Pydantic schemas for API contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class MemberSyncItem(BaseModel):
    display_name: str
    ha_user_id: str | None = None
    ha_person_entity_id: str | None = None
    notify_service: str | None = None
    active: bool = True


class MembersSyncRequest(BaseModel):
    members: list[MemberSyncItem]


class MemberResponse(BaseModel):
    id: int
    display_name: str
    ha_user_id: str | None
    ha_person_entity_id: str | None
    notify_service: str | None
    active: bool


class ShoppingItemCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    actor_user_id: str | None = None


class ShoppingItemActionRequest(BaseModel):
    actor_user_id: str | None = None


class ShoppingFavoriteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    actor_user_id: str | None = None


class ShoppingItemResponse(BaseModel):
    id: int
    name: str
    status: str
    added_by_member_id: int | None
    added_at: datetime
    completed_by_member_id: int | None
    completed_at: datetime | None
    deleted_by_member_id: int | None
    deleted_at: datetime | None


class DistributionEntry(BaseModel):
    member_id: int
    name: str
    count: int
    percent: float


class BuyStatsResponse(BaseModel):
    window_days: int
    total_completed: int
    unknown_excluded_count: int
    distribution: list[DistributionEntry]
    svg_render_version: str


class ActivityEventResponse(BaseModel):
    id: int
    domain: str
    action: str
    actor_member_id: int | None
    actor_user_id_raw: str | None
    payload_json: dict[str, Any]
    created_at: datetime


class CleaningMarkDoneRequest(BaseModel):
    week_start: date
    actor_user_id: str | None = None
    completed_by_member_id: int | None = None


class CleaningMarkUndoneRequest(BaseModel):
    week_start: date
    actor_user_id: str | None = None


class CleaningMarkTakeoverDoneRequest(BaseModel):
    week_start: date
    original_assignee_member_id: int
    cleaner_member_id: int
    actor_user_id: str | None = None


class CleaningSwapRequest(BaseModel):
    week_start: date
    member_a_id: int
    member_b_id: int
    actor_user_id: str | None = None
    cancel: bool = False


class ManualImportRequest(BaseModel):
    rotation_rows: str | None = None
    cleaning_history_rows: str | None = None
    shopping_history_rows: str | None = None
    cleaning_override_rows: str | None = None
    actor_user_id: str | None = None


class NotificationItem(BaseModel):
    member_id: int | None
    notify_service: str | None
    title: str
    message: str


class MembersSyncResponse(BaseModel):
    members: list[MemberResponse]
    notifications: list[NotificationItem] = Field(default_factory=list)


class ManualImportResponse(BaseModel):
    ok: bool = True
    notifications: list[NotificationItem] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


# Backward-compat aliases for older references.
FlatasticImportRequest = ManualImportRequest
FlatasticImportResponse = ManualImportResponse


class CleaningNotificationDueResponse(BaseModel):
    notifications: list[NotificationItem]


class CleaningCurrentResponse(BaseModel):
    week_start: date
    baseline_assignee_member_id: int | None
    effective_assignee_member_id: int | None
    status: str
    completed_by_member_id: int | None


class CleaningScheduleRow(BaseModel):
    week_start: date
    baseline_assignee_member_id: int | None
    effective_assignee_member_id: int | None
    override_type: str | None
    override_source: str | None = None
    status: str | None = None
    completed_by_member_id: int | None = None
    completion_mode: str | None = None


class CleaningScheduleResponse(BaseModel):
    schedule: list[CleaningScheduleRow]


class OperationResponse(BaseModel):
    ok: bool = True
    id: int | None = None
    notifications: list[NotificationItem] = Field(default_factory=list)


class RecentsResponse(BaseModel):
    recents: list[str]


class FavoritesResponse(BaseModel):
    favorites: list[dict[str, Any]]
