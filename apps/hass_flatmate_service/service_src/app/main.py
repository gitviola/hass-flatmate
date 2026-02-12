"""FastAPI entrypoint for hass-flatmate add-on service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import db
from .db import Base, get_session
from .models import Member
from .schemas import (
    BuyStatsResponse,
    CleaningCurrentResponse,
    CleaningMarkDoneRequest,
    CleaningMarkUndoneRequest,
    CleaningMarkTakeoverDoneRequest,
    CleaningNotificationDispatchRequest,
    CleaningNotificationDueResponse,
    CleaningScheduleResponse,
    CleaningSwapRequest,
    ManualImportRequest,
    ManualImportResponse,
    FavoritesResponse,
    MemberResponse,
    MembersSyncResponse,
    MembersSyncRequest,
    OperationResponse,
    RecentsResponse,
    ShoppingFavoriteCreateRequest,
    ShoppingItemActionRequest,
    ShoppingItemCreateRequest,
    ShoppingItemResponse,
)
from .services import cleaning, importer, shopping
from .services.activity import list_events
from .services.members import sync_members
from .settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.configure_engine()
    db.ensure_db_dir()
    assert db.engine is not None
    Base.metadata.create_all(bind=db.engine)
    yield


app = FastAPI(title="hass-flatmate-service", version="0.1.21", lifespan=lifespan)


def require_token(x_flatmate_token: str | None = Header(default=None)) -> None:
    if x_flatmate_token != settings.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/v1/members", response_model=list[MemberResponse], dependencies=[Depends(require_token)])
def get_members(session: Session = Depends(get_session)) -> list[MemberResponse]:
    rows = session.execute(select(Member).order_by(Member.display_name.asc())).scalars().all()
    return [
        MemberResponse(
            id=row.id,
            display_name=row.display_name,
            ha_user_id=row.ha_user_id,
            ha_person_entity_id=row.ha_person_entity_id,
            notify_service=row.notify_service,
            active=row.active,
        )
        for row in rows
    ]


@app.put("/v1/members/sync", response_model=MembersSyncResponse, dependencies=[Depends(require_token)])
def put_members_sync(
    payload: MembersSyncRequest,
    session: Session = Depends(get_session),
) -> MembersSyncResponse:
    rows, deactivated_member_ids = sync_members(session, payload.members)
    cleaning.sync_rotation_members(session)
    inactive_member_ids = {
        int(row.id)
        for row in rows
        if getattr(row, "id", None) is not None and not bool(getattr(row, "active", True))
    }
    notifications = cleaning.cancel_overrides_for_inactive_members(
        session,
        inactive_member_ids=inactive_member_ids,
        actor_user_id=None,
    )
    return MembersSyncResponse(
        members=[
            MemberResponse(
                id=row.id,
                display_name=row.display_name,
                ha_user_id=row.ha_user_id,
                ha_person_entity_id=row.ha_person_entity_id,
                notify_service=row.notify_service,
                active=row.active,
            )
            for row in rows
        ],
        notifications=notifications,
    )


@app.get("/v1/shopping/items", response_model=list[ShoppingItemResponse], dependencies=[Depends(require_token)])
def get_shopping_items(session: Session = Depends(get_session)) -> list[ShoppingItemResponse]:
    rows = shopping.list_items(session)
    return [
        ShoppingItemResponse(
            id=row.id,
            name=row.name,
            status=row.status.value,
            added_by_member_id=row.added_by_member_id,
            added_at=row.added_at,
            completed_by_member_id=row.completed_by_member_id,
            completed_at=row.completed_at,
            deleted_by_member_id=row.deleted_by_member_id,
            deleted_at=row.deleted_at,
        )
        for row in rows
    ]


@app.post("/v1/shopping/items", response_model=OperationResponse, dependencies=[Depends(require_token)])
def post_shopping_items(
    payload: ShoppingItemCreateRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    item = shopping.add_item(session, payload.name, payload.actor_user_id)
    return OperationResponse(ok=True, id=item.id)


@app.post(
    "/v1/shopping/items/{item_id}/complete",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def post_shopping_complete(
    item_id: int,
    payload: ShoppingItemActionRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        item = shopping.complete_item(session, item_id, payload.actor_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True, id=item.id)


@app.delete(
    "/v1/shopping/items/{item_id}",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def delete_shopping_item(
    item_id: int,
    payload: ShoppingItemActionRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        item = shopping.delete_item(session, item_id, payload.actor_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True, id=item.id)


@app.get("/v1/shopping/recents", response_model=RecentsResponse, dependencies=[Depends(require_token)])
def get_shopping_recents(
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_session),
) -> RecentsResponse:
    return RecentsResponse(recents=shopping.recent_item_names(session, limit=limit))


@app.get("/v1/shopping/favorites", response_model=FavoritesResponse, dependencies=[Depends(require_token)])
def get_shopping_favorites(session: Session = Depends(get_session)) -> FavoritesResponse:
    rows = shopping.list_favorites(session)
    return FavoritesResponse(
        favorites=[
            {
                "id": row.id,
                "name": row.name,
                "created_by_member_id": row.created_by_member_id,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    )


@app.post(
    "/v1/shopping/favorites",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def post_shopping_favorite(
    payload: ShoppingFavoriteCreateRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    favorite = shopping.add_favorite(session, payload.name, payload.actor_user_id)
    return OperationResponse(ok=True, id=favorite.id)


@app.delete(
    "/v1/shopping/favorites/{favorite_id}",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def delete_shopping_favorite(
    favorite_id: int,
    payload: ShoppingItemActionRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        shopping.delete_favorite(session, favorite_id, payload.actor_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True)


@app.get("/v1/stats/buys", response_model=BuyStatsResponse, dependencies=[Depends(require_token)])
def get_buy_stats(
    window_days: int = Query(default=90, ge=1, le=3650),
    session: Session = Depends(get_session),
) -> BuyStatsResponse:
    return BuyStatsResponse(**shopping.buy_distribution(session, window_days=window_days))


@app.get(
    "/v1/stats/buys.svg",
    response_class=PlainTextResponse,
    dependencies=[Depends(require_token)],
)
def get_buy_stats_svg(
    window_days: int = Query(default=90, ge=1, le=3650),
    session: Session = Depends(get_session),
) -> Response:
    stats = shopping.buy_distribution(session, window_days=window_days)
    svg = shopping.distribution_svg(stats)
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/v1/activity", dependencies=[Depends(require_token)])
def get_activity(
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = list_events(session, limit=limit)
    return [
        {
            "id": row.id,
            "domain": row.domain,
            "action": row.action,
            "actor_member_id": row.actor_member_id,
            "actor_user_id_raw": row.actor_user_id_raw,
            "payload_json": row.payload_json,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.post(
    "/v1/import/manual",
    response_model=ManualImportResponse,
    dependencies=[Depends(require_token)],
)
@app.post(
    "/v1/import/flatastic",
    response_model=ManualImportResponse,
    dependencies=[Depends(require_token)],
    include_in_schema=False,
)
def post_import_manual(
    payload: ManualImportRequest,
    session: Session = Depends(get_session),
) -> ManualImportResponse:
    try:
        summary, notifications = importer.import_manual_data(
            session,
            rotation_rows=payload.rotation_rows,
            cleaning_history_rows=payload.cleaning_history_rows,
            shopping_history_rows=payload.shopping_history_rows,
            cleaning_override_rows=payload.cleaning_override_rows,
            actor_user_id=payload.actor_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ManualImportResponse(ok=True, notifications=notifications, summary=summary)


@app.get("/v1/cleaning/current", response_model=CleaningCurrentResponse, dependencies=[Depends(require_token)])
def get_cleaning_current(session: Session = Depends(get_session)) -> CleaningCurrentResponse:
    return CleaningCurrentResponse(**cleaning.get_cleaning_current(session))


@app.get(
    "/v1/cleaning/schedule",
    response_model=CleaningScheduleResponse,
    dependencies=[Depends(require_token)],
)
def get_cleaning_schedule(
    weeks_ahead: int = Query(default=12, ge=1, le=104),
    include_previous_weeks: int = Query(default=0, ge=0, le=8),
    session: Session = Depends(get_session),
) -> CleaningScheduleResponse:
    rows = cleaning.get_schedule(
        session,
        weeks_ahead=weeks_ahead + include_previous_weeks,
        from_week_start=cleaning.add_weeks(cleaning.week_start_for(cleaning.now_utc()), -include_previous_weeks),
    )
    return CleaningScheduleResponse(schedule=rows)


@app.post(
    "/v1/cleaning/mark_done",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def post_mark_done(
    payload: CleaningMarkDoneRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        notifications = cleaning.mark_cleaning_done(
            session,
            week_start=payload.week_start,
            actor_user_id=payload.actor_user_id,
            completed_by_member_id=payload.completed_by_member_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True, notifications=notifications)


@app.post(
    "/v1/cleaning/mark_undone",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def post_mark_undone(
    payload: CleaningMarkUndoneRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        notifications = cleaning.mark_cleaning_undone(
            session,
            week_start=payload.week_start,
            actor_user_id=payload.actor_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True, notifications=notifications)


@app.post(
    "/v1/cleaning/mark_takeover_done",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def post_mark_takeover_done(
    payload: CleaningMarkTakeoverDoneRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        notifications = cleaning.mark_cleaning_takeover_done(
            session,
            week_start=payload.week_start,
            original_assignee_member_id=payload.original_assignee_member_id,
            cleaner_member_id=payload.cleaner_member_id,
            actor_user_id=payload.actor_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True, notifications=notifications)


@app.post(
    "/v1/cleaning/overrides/swap",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def post_swap_override(
    payload: CleaningSwapRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        override, notifications = cleaning.upsert_manual_swap(
            session,
            week_start=payload.week_start,
            member_a_id=payload.member_a_id,
            member_b_id=payload.member_b_id,
            actor_user_id=payload.actor_user_id,
            cancel=payload.cancel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True, id=override.id if override else None, notifications=notifications)


@app.get(
    "/v1/cleaning/notifications/due",
    response_model=CleaningNotificationDueResponse,
    dependencies=[Depends(require_token)],
)
def get_due_notifications(
    at: str = Query(..., description="ISO datetime in HA timezone"),
    session: Session = Depends(get_session),
) -> CleaningNotificationDueResponse:
    try:
        moment = datetime.fromisoformat(at)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid datetime format") from exc

    notifications = cleaning.due_notifications(session, at=moment)
    return CleaningNotificationDueResponse(notifications=notifications)


@app.post(
    "/v1/cleaning/notifications/dispatch",
    response_model=OperationResponse,
    dependencies=[Depends(require_token)],
)
def post_cleaning_notification_dispatch(
    payload: CleaningNotificationDispatchRequest,
    session: Session = Depends(get_session),
) -> OperationResponse:
    try:
        cleaning.record_notification_dispatches(
            session,
            records=[record.model_dump() for record in payload.records],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OperationResponse(ok=True)
