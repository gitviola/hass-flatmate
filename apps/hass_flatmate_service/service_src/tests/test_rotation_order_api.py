"""Interactive rotation order (GET/PUT /v1/cleaning/rotation) tests."""

from __future__ import annotations

from datetime import date, timedelta


def _sync_members(client, headers) -> dict[str, int]:
    payload = {
        "members": [
            {"display_name": "Alex", "ha_user_id": "u1", "notify_service": "notify.mobile_app_alex", "active": True},
            {"display_name": "Sam", "ha_user_id": "u2", "notify_service": "notify.mobile_app_sam", "active": True},
            {"display_name": "Pat", "ha_user_id": "u3", "notify_service": "notify.mobile_app_pat", "active": True},
        ]
    }
    response = client.put("/v1/members/sync", headers=headers, json=payload)
    assert response.status_code == 200
    return {row["display_name"]: row["id"] for row in response.json()["members"]}


def _schedule_assignees(client, headers, weeks: int) -> list[int]:
    response = client.get(f"/v1/cleaning/schedule?weeks_ahead={weeks}", headers=headers)
    assert response.status_code == 200
    return [row["effective_assignee_member_id"] for row in response.json()["schedule"]]


def test_get_rotation_starts_with_current_week_assignee(client, auth_headers) -> None:
    _sync_members(client, auth_headers)
    current = client.get("/v1/cleaning/current", headers=auth_headers).json()

    response = client.get("/v1/cleaning/rotation", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    week_start = date.fromisoformat(payload["week_start"])
    assert week_start.weekday() == 0
    members = payload["members"]
    assert len(members) == 3
    assert members[0]["member_id"] == current["effective_assignee_member_id"]
    assert [date.fromisoformat(m["week_start"]) for m in members] == [
        week_start + timedelta(weeks=i) for i in range(3)
    ]
    assert [m["member_id"] for m in members] == _schedule_assignees(client, auth_headers, 3)


def test_put_rotation_reorders_schedule_without_notifications(client, auth_headers) -> None:
    ids = _sync_members(client, auth_headers)
    client.get("/v1/cleaning/current", headers=auth_headers)  # materialize current week assignment

    new_order = [ids["Pat"], ids["Alex"], ids["Sam"]]
    response = client.put("/v1/cleaning/rotation", headers=auth_headers, json={"member_ids": new_order})
    assert response.status_code == 200
    body = response.json()
    assert [m["member_id"] for m in body["members"]] == new_order
    assert "notifications" not in body

    assert client.get("/v1/cleaning/current", headers=auth_headers).json()["effective_assignee_member_id"] == ids["Pat"]
    assert _schedule_assignees(client, auth_headers, 6) == new_order + new_order
    assert [m["member_id"] for m in client.get("/v1/cleaning/rotation", headers=auth_headers).json()["members"]] == new_order

    activity = client.get("/v1/activity", headers=auth_headers).json()
    rows = activity if isinstance(activity, list) else activity.get("events", activity.get("items", []))
    assert any(row.get("action") == "rotation_reordered" for row in rows)


def test_put_rotation_rejects_incomplete_or_duplicate_order(client, auth_headers) -> None:
    ids = _sync_members(client, auth_headers)

    missing = client.put("/v1/cleaning/rotation", headers=auth_headers, json={"member_ids": [ids["Alex"], ids["Sam"]]})
    assert missing.status_code == 400

    dup = client.put(
        "/v1/cleaning/rotation",
        headers=auth_headers,
        json={"member_ids": [ids["Alex"], ids["Alex"], ids["Sam"]]},
    )
    assert dup.status_code == 400

    unknown = client.put(
        "/v1/cleaning/rotation",
        headers=auth_headers,
        json={"member_ids": [ids["Alex"], ids["Sam"], 999]},
    )
    assert unknown.status_code == 400


def test_put_rotation_keeps_completed_current_week(client, auth_headers) -> None:
    ids = _sync_members(client, auth_headers)
    current = client.get("/v1/cleaning/current", headers=auth_headers).json()
    done_by = current["effective_assignee_member_id"]
    week_start = current["week_start"]
    assert client.post(
        "/v1/cleaning/mark_done", headers=auth_headers, json={"week_start": week_start}
    ).status_code == 200

    others = [member_id for member_id in ids.values() if member_id != done_by]
    new_order = others + [done_by]
    assert client.put("/v1/cleaning/rotation", headers=auth_headers, json={"member_ids": new_order}).status_code == 200

    after = client.get("/v1/cleaning/current", headers=auth_headers).json()
    assert after["effective_assignee_member_id"] == done_by
    assert after["status"] == "done"


def test_rotation_requires_token(client) -> None:
    assert client.get("/v1/cleaning/rotation").status_code == 401
    assert client.put("/v1/cleaning/rotation", json={"member_ids": []}).status_code == 401


def _setup_with_history(client, headers) -> tuple[dict[str, int], dict]:
    ids = _sync_members(client, headers)
    current = client.get("/v1/cleaning/current", headers=headers).json()
    week_start = date.fromisoformat(current["week_start"])
    # history: last week done, plus a planned swap three weeks out
    client.post("/v1/cleaning/mark_done", headers=headers, json={"week_start": (week_start - timedelta(weeks=1)).isoformat()})
    client.post(
        "/v1/cleaning/overrides/swap",
        headers=headers,
        json={"week_start": (week_start + timedelta(weeks=3)).isoformat(), "member_a_id": ids["Alex"], "member_b_id": ids["Sam"]},
    )
    return ids, current


def test_put_rotation_matches_manual_import_service(client, tmp_path, auth_headers) -> None:
    """Saving in the editor must leave the same state as the rotation_rows import service."""
    from app import db
    from app.db import Base

    results = []
    for mode in ("service", "editor"):
        # fresh database per mode, reusing the fixture's authenticated client
        db.configure_engine(f"sqlite:///{tmp_path / (mode + '.db')}")
        Base.metadata.create_all(bind=db.engine)
        ids, current = _setup_with_history(client, auth_headers)
        order = [ids["Pat"], ids["Sam"], ids["Alex"]]
        if mode == "service":
            week_start = date.fromisoformat(current["week_start"])
            names = {v: k for k, v in ids.items()}
            rows = "\n".join(
                f"{(week_start + timedelta(weeks=i)).isoformat()},{names[member_id]}"
                for i, member_id in enumerate(order)
            )
            response = client.post("/v1/import/manual", headers=auth_headers, json={"rotation_rows": rows})
        else:
            response = client.put("/v1/cleaning/rotation", headers=auth_headers, json={"member_ids": order})
        assert response.status_code == 200, response.text
        schedule = client.get(
            "/v1/cleaning/schedule?weeks_ahead=9&include_previous_weeks=2", headers=auth_headers
        ).json()["schedule"]
        results.append([
            (row["week_start"], row["baseline_assignee_member_id"], row["effective_assignee_member_id"], row["status"])
            for row in schedule
        ])

    assert results[0] == results[1]
