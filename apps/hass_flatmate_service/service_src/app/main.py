"""FastAPI entrypoint for hass-flatmate add-on service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import json

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import db
from .db import Base, get_session
from .models import (
    ActivityEvent,
    CleaningAssignment,
    CleaningOverride,
    Member,
    RotationConfig,
    ShoppingFavorite,
    ShoppingItem,
)
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
    SnapshotExportResponse,
    SnapshotImportRequest,
    SnapshotImportResponse,
)
from .services import cleaning, importer, shopping, snapshot
from .services.activity import list_events
from .services.members import sync_members
from .settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.configure_engine()
    db.ensure_db_dir()
    assert db.engine is not None
    Base.metadata.create_all(bind=db.engine)

    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(db.engine)
    columns = {c["name"] for c in inspector.get_columns("cleaning_assignments")}
    if "notified_slots" not in columns:
        with db.engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE cleaning_assignments ADD COLUMN notified_slots JSON DEFAULT NULL"
            ))

    member_columns = {c["name"] for c in inspector.get_columns("members")}
    with db.engine.begin() as conn:
        if "notify_services" not in member_columns:
            conn.execute(text("ALTER TABLE members ADD COLUMN notify_services JSON DEFAULT '[]'"))
        if "device_trackers" not in member_columns:
            conn.execute(text("ALTER TABLE members ADD COLUMN device_trackers JSON DEFAULT '[]'"))

    yield


app = FastAPI(title="hass-flatmate-service", version="0.1.43", lifespan=lifespan)


def require_token(x_flatmate_token: str | None = Header(default=None)) -> None:
    if x_flatmate_token != settings.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def ingress_migration_ui() -> str:
    ui_html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Hass Flatmate Migration</title>
    <style>
      :root {
        color-scheme: light dark;
        --bg: #0f172a;
        --bg-card: #111827;
        --fg: #e5e7eb;
        --muted: #93c5fd;
        --accent: #22c55e;
        --danger: #f87171;
      }

      body {
        margin: 0;
        padding: 20px;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        background: radial-gradient(circle at top, #1e293b 0%, var(--bg) 55%);
        color: var(--fg);
      }

      .wrap {
        max-width: 980px;
        margin: 0 auto;
      }

      .card {
        background: color-mix(in srgb, var(--bg-card) 90%, black);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
      }

      h1 {
        margin: 0 0 8px;
        font-size: 24px;
      }

      p {
        margin: 6px 0;
      }

      .muted {
        color: var(--muted);
      }

      .row {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
      }

      input[type="password"],
      input[type="text"],
      textarea,
      select {
        width: 100%;
        box-sizing: border-box;
        border: 1px solid #475569;
        background: #0b1220;
        color: var(--fg);
        border-radius: 8px;
        padding: 10px 12px;
        font: inherit;
      }

      textarea {
        min-height: 320px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        line-height: 1.35;
      }

      .token {
        flex: 1;
        min-width: 260px;
      }

      button {
        border: 1px solid #475569;
        background: #1f2937;
        color: var(--fg);
        border-radius: 8px;
        padding: 10px 14px;
        cursor: pointer;
        font: inherit;
      }

      button.primary {
        background: #14532d;
        border-color: #166534;
      }

      button.warn {
        background: #7f1d1d;
        border-color: #991b1b;
      }

      button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }

      .status {
        margin-top: 10px;
        min-height: 22px;
      }

      .status.ok {
        color: var(--accent);
      }

      .status.err {
        color: var(--danger);
      }

      .label {
        font-size: 13px;
        color: #cbd5e1;
      }

      .grow {
        flex: 1;
      }

      .table-wrap {
        overflow-x: auto;
      }

      table {
        width: 100%;
        border-collapse: collapse;
      }

      th,
      td {
        text-align: left;
        vertical-align: top;
        border-bottom: 1px solid #334155;
        padding: 10px 8px;
        font-size: 14px;
      }

      th {
        color: #cbd5e1;
        font-weight: 600;
      }

      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }

      .chip {
        border: 1px solid #475569;
        background: #0b1220;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 12px;
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <h1>Hass Flatmate Snapshot Migration</h1>
        <p class="muted">Export your real Home Assistant data and import it locally for testing edge cases.</p>
        <p class="muted">Uses your configured add-on token automatically.</p>
      </div>

      <div class="card">
        <div class="row">
          <strong>Member Notification Mapping</strong>
          <button id="load-members">Load members & devices</button>
        </div>
        <div class="muted" style="margin-top:8px">Uses Home Assistant person entities and phone trackers (not guessed device names).</div>
        <div class="status" id="members-status"></div>
        <div id="members-table" class="table-wrap" style="margin-top:10px"></div>
      </div>

      <div class="card">
        <div class="row">
          <button id="export">Export snapshot</button>
          <button id="download">Download JSON</button>
          <label class="grow"></label>
        </div>
        <div class="status" id="export-status"></div>
      </div>

      <div class="card">
        <div class="row">
          <input id="file" type="file" accept="application/json,.json" />
          <button id="load-file">Load file into editor</button>
        </div>
        <div style="margin-top:10px" class="label">Snapshot JSON (editable)</div>
        <textarea id="editor" placeholder='{"schema_version":1,"data":{...}}'></textarea>
      </div>

      <div class="card">
        <div class="row">
          <label><input id="replace" type="checkbox" checked /> Replace existing local data before import</label>
        </div>
        <div class="row" style="margin-top:10px">
          <button id="import" class="primary">Import snapshot</button>
          <button id="clear" class="warn">Clear editor</button>
        </div>
        <div class="status" id="import-status"></div>
      </div>
    </div>

    <script>
      const API_TOKEN = __API_TOKEN__;
      const editor = document.getElementById("editor");
      const replaceInput = document.getElementById("replace");
      const exportStatus = document.getElementById("export-status");
      const importStatus = document.getElementById("import-status");
      const fileInput = document.getElementById("file");
      const membersStatus = document.getElementById("members-status");
      const membersTable = document.getElementById("members-table");

      const setStatus = (target, message, ok) => {
        target.textContent = message || "";
        target.className = ok == null ? "status" : ok ? "status ok" : "status err";
      };

      const authHeaders = (includeJson) => {
        const headers = {"x-flatmate-token": API_TOKEN};
        if (includeJson) headers["content-type"] = "application/json";
        return headers;
      };

      const parseError = async (response) => {
        const text = await response.text();
        if (!text) {
          return response.status + " " + response.statusText;
        }
        try {
          const payload = JSON.parse(text);
          if (payload && typeof payload === "object") {
            return payload.detail || payload.message || text;
          }
          return text;
        } catch (_err) {
          return text;
        }
      };

      const escapeHtml = (value) => String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");

      const renderChips = (values) => {
        if (!Array.isArray(values) || values.length === 0) {
          return '<span class="muted">none</span>';
        }
        return '<div class="chips">' + values
          .map((value) => '<span class="chip">' + escapeHtml(value) + '</span>')
          .join("") + '</div>';
      };

      const loadMembers = async () => {
        setStatus(membersStatus, "Loading members...", null);
        try {
          const response = await fetch("/v1/members", {
            method: "GET",
            headers: authHeaders(false),
          });
          if (!response.ok) {
            throw new Error(await parseError(response));
          }
          const rows = await response.json();
          if (!Array.isArray(rows) || rows.length === 0) {
            membersTable.innerHTML = '<p class="muted">No members synced yet.</p>';
            setStatus(membersStatus, "No members found.", true);
            return;
          }
          membersTable.innerHTML =
            '<table>' +
            '<thead><tr><th>Name</th><th>Person Entity</th><th>Device Trackers</th><th>Notify Services</th></tr></thead>' +
            '<tbody>' + rows.map((row) =>
              '<tr>' +
              '<td>' + escapeHtml(row.display_name) + (row.active ? "" : ' <span class="muted">(inactive)</span>') + '</td>' +
              '<td>' + escapeHtml(row.ha_person_entity_id || "none") + '</td>' +
              '<td>' + renderChips(row.device_trackers) + '</td>' +
              '<td>' + renderChips(row.notify_services) + '</td>' +
              '</tr>'
            ).join("") + '</tbody></table>';
          setStatus(membersStatus, "Loaded " + rows.length + " member mapping(s).", true);
        } catch (err) {
          membersTable.innerHTML = "";
          setStatus(membersStatus, "Failed to load members: " + (err?.message || String(err)), false);
        }
      };

      document.getElementById("load-members").addEventListener("click", loadMembers);

      document.getElementById("export").addEventListener("click", async () => {
        setStatus(exportStatus, "Exporting snapshot...", null);
        try {
          const response = await fetch("/v1/admin/export", {
            method: "GET",
            headers: authHeaders(false),
          });
          if (!response.ok) {
            throw new Error(await parseError(response));
          }
          const payload = await response.json();
          editor.value = JSON.stringify(payload, null, 2);
          const generatedAt = payload?.generated_at || "unknown time";
          setStatus(exportStatus, "Snapshot exported (" + generatedAt + ").", true);
        } catch (err) {
          setStatus(exportStatus, "Export failed: " + (err?.message || String(err)), false);
        }
      });

      document.getElementById("download").addEventListener("click", () => {
        const text = editor.value.trim();
        if (!text) {
          setStatus(exportStatus, "Nothing to download. Export or paste snapshot JSON first.", false);
          return;
        }
        const blob = new Blob([text], {type: "application/json"});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        const stamp = new Date().toISOString().replaceAll(":", "-");
        a.href = url;
        a.download = "hass-flatmate-snapshot-" + stamp + ".json";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        setStatus(exportStatus, "Snapshot downloaded.", true);
      });

      document.getElementById("load-file").addEventListener("click", async () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
          setStatus(importStatus, "Select a JSON file first.", false);
          return;
        }
        try {
          editor.value = await file.text();
          setStatus(importStatus, "Loaded file into editor.", true);
        } catch (err) {
          setStatus(importStatus, "Failed to read file: " + (err?.message || String(err)), false);
        }
      });

      document.getElementById("import").addEventListener("click", async () => {
        const raw = editor.value.trim();
        if (!raw) {
          setStatus(importStatus, "Paste or load snapshot JSON before importing.", false);
          return;
        }
        let snapshot;
        try {
          snapshot = JSON.parse(raw);
        } catch (err) {
          setStatus(importStatus, "Invalid JSON: " + (err?.message || String(err)), false);
          return;
        }

        setStatus(importStatus, "Importing snapshot...", null);
        try {
          const response = await fetch("/v1/admin/import", {
            method: "POST",
            headers: authHeaders(true),
            body: JSON.stringify({
              snapshot,
              replace_existing: !!replaceInput.checked,
            }),
          });
          if (!response.ok) {
            throw new Error(await parseError(response));
          }
          const payload = await response.json();
          setStatus(importStatus, "Import finished: " + JSON.stringify(payload.summary || {}), true);
        } catch (err) {
          setStatus(importStatus, "Import failed: " + (err?.message || String(err)), false);
        }
      });

      document.getElementById("clear").addEventListener("click", () => {
        editor.value = "";
        setStatus(importStatus, "Editor cleared.", true);
      });

      loadMembers();
    </script>
  </body>
</html>
"""
    return ui_html.replace("__API_TOKEN__", json.dumps(settings.api_token))


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
            notify_services=list(row.notify_services or []),
            device_trackers=list(row.device_trackers or []),
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
                notify_services=list(row.notify_services or []),
                device_trackers=list(row.device_trackers or []),
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


@app.post("/v1/admin/reset", response_model=OperationResponse, dependencies=[Depends(require_token)])
def post_admin_reset(session: Session = Depends(get_session)) -> OperationResponse:
    session.execute(delete(CleaningOverride))
    session.execute(delete(CleaningAssignment))
    session.execute(delete(ActivityEvent))
    session.execute(delete(ShoppingItem))
    session.execute(delete(ShoppingFavorite))
    session.execute(delete(RotationConfig))
    session.execute(delete(Member))
    session.commit()
    return OperationResponse(ok=True)


@app.get("/v1/admin/export", response_model=SnapshotExportResponse, dependencies=[Depends(require_token)])
def get_admin_export(session: Session = Depends(get_session)) -> SnapshotExportResponse:
    payload = snapshot.export_snapshot(session)
    return SnapshotExportResponse(**payload)


@app.post("/v1/admin/import", response_model=SnapshotImportResponse, dependencies=[Depends(require_token)])
def post_admin_import(
    payload: SnapshotImportRequest,
    session: Session = Depends(get_session),
) -> SnapshotImportResponse:
    try:
        summary = snapshot.import_snapshot(
            session,
            snapshot=payload.snapshot,
            replace_existing=payload.replace_existing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SnapshotImportResponse(ok=True, summary=summary)


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
            return_week_start=payload.return_week_start,
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
