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


def test_import_creates_inactive_placeholder_for_unknown_member(client, auth_headers) -> None:
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
    assert response.status_code == 200

    members = client.get("/v1/members", headers=auth_headers).json()
    placeholder = [m for m in members if m["display_name"] == "Unknown Person"]
    assert len(placeholder) == 1
    assert placeholder[0]["active"] is False
    assert placeholder[0]["ha_user_id"] is None


def test_admin_reset_clears_all_data_including_members(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    # Import some data first
    client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={
            "rotation_rows": ";".join([
                f"{(week_start + timedelta(days=2)).isoformat()},Alex",
                f"{(week_start + timedelta(days=9)).isoformat()},Sam",
            ]),
            "cleaning_history_rows": f"{(week_start + timedelta(days=2)).isoformat()},Alex,done",
            "shopping_history_rows": f"{week_start.isoformat()},Milk,Alex",
            "actor_user_id": "u1",
        },
    )

    # Add a shopping item and favorite
    client.post("/v1/shopping/items", headers=auth_headers, json={"name": "Bread", "actor_user_id": "u1"})
    client.post("/v1/shopping/favorites", headers=auth_headers, json={"name": "Eggs", "actor_user_id": "u1"})

    # Verify data exists
    assert len(client.get("/v1/shopping/items", headers=auth_headers).json()) > 0
    assert len(client.get("/v1/shopping/favorites", headers=auth_headers).json()["favorites"]) > 0
    assert len(client.get("/v1/activity?limit=50", headers=auth_headers).json()) > 0

    # Reset
    response = client.post("/v1/admin/reset", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # Everything is gone including members
    assert client.get("/v1/shopping/items", headers=auth_headers).json() == []
    assert client.get("/v1/shopping/favorites", headers=auth_headers).json()["favorites"] == []
    assert client.get("/v1/activity?limit=50", headers=auth_headers).json() == []
    assert client.get("/v1/members", headers=auth_headers).json() == []

    # HA sync recreates active members
    _sync_members(client, auth_headers)
    members = client.get("/v1/members", headers=auth_headers).json()
    names = sorted(m["display_name"] for m in members)
    assert names == ["Alex", "Pat", "Sam"]


def test_reset_then_reimport_with_former_flatmates(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    # First import references a former flatmate "Jordan" who left
    first_import = client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={
            "rotation_rows": ";".join([
                f"{(week_start - timedelta(days=21)).isoformat()},Jordan",
                f"{(week_start - timedelta(days=14)).isoformat()},Alex",
                f"{(week_start - timedelta(days=7)).isoformat()},Sam",
                f"{(week_start + timedelta(days=2)).isoformat()},Pat",
            ]),
            "cleaning_history_rows": ";".join([
                f"{(week_start - timedelta(days=19)).isoformat()},Jordan,done",
                f"{(week_start - timedelta(days=12)).isoformat()},Alex,done",
                f"{(week_start - timedelta(days=5)).isoformat()},Sam,done",
            ]),
            "shopping_history_rows": ";".join([
                f"{(week_start - timedelta(days=20)).isoformat()},Milk,Jordan",
                f"{(week_start - timedelta(days=13)).isoformat()},Bread,Alex",
            ]),
            "actor_user_id": "u1",
        },
    )
    assert first_import.status_code == 200
    summary = first_import.json()["summary"]
    assert summary["rotation_weeks_imported"] == 4
    assert "Jordan" in summary["rotation_order_names"]

    # Jordan was auto-created as inactive
    members = client.get("/v1/members", headers=auth_headers).json()
    jordan = [m for m in members if m["display_name"] == "Jordan"]
    assert len(jordan) == 1
    assert jordan[0]["active"] is False

    # Activity includes Jordan's shopping
    activity = client.get("/v1/activity?limit=50", headers=auth_headers).json()
    shopping_events = [
        e for e in activity
        if e["action"] == "shopping_item_completed" and e["actor_member_id"] == jordan[0]["id"]
    ]
    assert len(shopping_events) == 1

    # Reset wipes everything including members, re-sync active ones from HA
    client.post("/v1/admin/reset", headers=auth_headers)
    assert client.get("/v1/members", headers=auth_headers).json() == []
    _sync_members(client, auth_headers)

    # Reimport — Jordan gets recreated as inactive placeholder
    second_import = client.post(
        "/v1/import/manual",
        headers=auth_headers,
        json={
            "rotation_rows": ";".join([
                f"{(week_start - timedelta(days=21)).isoformat()},Jordan",
                f"{(week_start - timedelta(days=14)).isoformat()},Alex",
                f"{(week_start - timedelta(days=7)).isoformat()},Sam",
                f"{(week_start + timedelta(days=2)).isoformat()},Pat",
            ]),
            "shopping_history_rows": f"{(week_start - timedelta(days=20)).isoformat()},Milk,Jordan",
            "actor_user_id": "u1",
        },
    )
    assert second_import.status_code == 200

    # Jordan was recreated as inactive, only one instance
    members_after = client.get("/v1/members", headers=auth_headers).json()
    jordans = [m for m in members_after if m["display_name"] == "Jordan"]
    assert len(jordans) == 1
    assert jordans[0]["active"] is False


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
