"""Manual migration import API tests."""

from __future__ import annotations

from datetime import date, timedelta


def _sync_members(client, headers) -> None:
    payload = {
        "members": [
            {"display_name": "Alex", "ha_user_id": "u1", "notify_service": "notify.mobile_app_alex", "active": True},
            {"display_name": "Sam", "ha_user_id": "u2", "notify_service": "notify.mobile_app_sam", "active": True},
            {"display_name": "Pat", "ha_user_id": "u3", "notify_service": "notify.mobile_app_pat", "active": True},
        ]
    }
    response = client.put("/v1/members/sync", headers=headers, json=payload)
    assert response.status_code == 200


def test_import_rotation_rows_sets_rotation_order(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    rotation_rows = ";".join(
        [
            f"{(week_start + timedelta(days=2)).isoformat()},Alex",
            f"{(week_start + timedelta(days=9)).isoformat()},Sam",
            f"{(week_start + timedelta(days=16)).isoformat()},Pat",
        ]
    )
    response = client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={"rotation_rows": rotation_rows, "actor_user_id": "u1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["rotation_weeks_imported"] == 3
    assert payload["summary"]["rotation_order_names"][:3] == ["Alex", "Sam", "Pat"]

    schedule = client.get("/v1/cleaning/schedule?weeks_ahead=3", headers=auth_headers)
    assert schedule.status_code == 200
    rows = schedule.json()["schedule"]
    assert [row["baseline_assignee_member_id"] for row in rows[:3]] == [1, 2, 3]


def test_import_history_rows_populates_cleaning_and_shopping(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])
    previous_week = week_start - timedelta(days=7)

    cleaning_rows = ";".join(
        [
            f"{(previous_week + timedelta(days=2)).isoformat()},Alex,done",
            f"{(week_start + timedelta(days=2)).isoformat()},Sam,done",
        ]
    )
    shopping_rows = ";".join(
        [
            f"{(week_start - timedelta(days=3)).isoformat()},Milk,Alex",
            f"{(week_start - timedelta(days=2)).isoformat()},Toilet Paper,Sam",
        ]
    )

    response = client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={
            "cleaning_history_rows": cleaning_rows,
            "shopping_history_rows": shopping_rows,
            "actor_user_id": "u1",
        },
    )
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["cleaning_history_rows_imported"] == 2
    assert summary["shopping_history_rows_imported"] == 2

    schedule = client.get(
        "/v1/cleaning/schedule?weeks_ahead=2&include_previous_weeks=1",
        headers=auth_headers,
    )
    assert schedule.status_code == 200
    rows = {date.fromisoformat(row["week_start"]): row for row in schedule.json()["schedule"]}
    assert rows[previous_week]["status"] == "done"

    stats = client.get("/v1/stats/buys?window_days=365", headers=auth_headers)
    assert stats.status_code == 200
    stats_payload = stats.json()
    assert stats_payload["total_completed"] == 2
    counts = {row["name"]: row["count"] for row in stats_payload["distribution"]}
    assert counts.get("Alex") == 1
    assert counts.get("Sam") == 1

    activity = client.get("/v1/activity?limit=10", headers=auth_headers)
    assert activity.status_code == 200
    actions = [row["action"] for row in activity.json()]
    assert "manual_import_applied" in actions


def test_import_rejects_unknown_member_name(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    response = client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={
            "rotation_rows": f"{(week_start + timedelta(days=2)).isoformat()},Unknown Person",
            "actor_user_id": "u1",
        },
    )
    assert response.status_code == 400
    assert "Unknown member" in response.json()["detail"]


def test_import_cleaning_override_rows_plans_compensation_override(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    rotation_rows = ";".join(
        [
            f"{(week_start + timedelta(days=2)).isoformat()},Alex",
            f"{(week_start + timedelta(days=9)).isoformat()},Sam",
            f"{(week_start + timedelta(days=16)).isoformat()},Pat",
        ]
    )
    override_rows = f"{(week_start + timedelta(days=9)).isoformat()},Sam,Alex,compensation"

    response = client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={
            "rotation_rows": rotation_rows,
            "cleaning_override_rows": override_rows,
            "actor_user_id": "u1",
        },
    )
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["cleaning_override_rows_imported"] == 1

    schedule = client.get("/v1/cleaning/schedule?weeks_ahead=3", headers=auth_headers)
    assert schedule.status_code == 200
    rows = schedule.json()["schedule"]
    assert rows[1]["baseline_assignee_member_id"] == 2  # Sam
    assert rows[1]["effective_assignee_member_id"] == 1  # Alex
    assert rows[1]["override_type"] == "compensation"


def test_import_swap_pair_links_rows_and_cancel_reverts_both_weeks(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])
    week_after = week_start + timedelta(days=7)

    rotation_rows = ";".join(
        [
            f"{(week_start + timedelta(days=2)).isoformat()},Alex",
            f"{(week_after + timedelta(days=2)).isoformat()},Sam",
            f"{(week_after + timedelta(days=9)).isoformat()},Pat",
        ]
    )
    cleaning_history_rows = f"{(week_start + timedelta(days=2)).isoformat()},Alex,done,Sam"
    cleaning_override_rows = ";".join(
        [
            f"{(week_start + timedelta(days=2)).isoformat()},Alex,Sam,manual_swap",
            f"{(week_after + timedelta(days=2)).isoformat()},Sam,Alex,compensation",
        ]
    )

    imported = client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={
            "rotation_rows": rotation_rows,
            "cleaning_history_rows": cleaning_history_rows,
            "cleaning_override_rows": cleaning_override_rows,
            "actor_user_id": "u1",
        },
    )
    assert imported.status_code == 200
    summary = imported.json()["summary"]
    assert summary["cleaning_override_rows_imported"] == 2
    assert summary["cleaning_override_swap_pairs_linked"] == 1

    schedule = client.get("/v1/cleaning/schedule?weeks_ahead=4", headers=auth_headers)
    assert schedule.status_code == 200
    row_map = {date.fromisoformat(row["week_start"]): row for row in schedule.json()["schedule"]}
    assert row_map[week_start]["override_type"] == "manual_swap"
    assert row_map[week_after]["override_type"] == "compensation"
    assert row_map[week_after]["override_source"] == "manual"
    assert row_map[week_after]["source_week_start"] == week_start.isoformat()

    canceled = client.post(
        "/v1/cleaning/overrides/swap",
        headers=auth_headers,
        json={
            "week_start": week_start.isoformat(),
            "member_a_id": 1,
            "member_b_id": 2,
            "actor_user_id": "u1",
            "cancel": True,
        },
    )
    assert canceled.status_code == 200

    after_cancel = client.get("/v1/cleaning/schedule?weeks_ahead=4", headers=auth_headers)
    assert after_cancel.status_code == 200
    row_map_after_cancel = {
        date.fromisoformat(row["week_start"]): row
        for row in after_cancel.json()["schedule"]
    }
    assert row_map_after_cancel[week_start]["override_type"] is None
    assert row_map_after_cancel[week_after]["override_type"] is None
