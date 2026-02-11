"""Cleaning rotation/override/notification tests."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta


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


def _iso_at(day: date, hh: int, mm: int = 0) -> str:
    return datetime.combine(day, time(hour=hh, minute=mm)).isoformat()


def test_rotation_swap_takeover_and_compensation(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    current_payload = current.json()
    week_start = date.fromisoformat(current_payload["week_start"])

    baseline = current_payload["baseline_assignee_member_id"]
    assert baseline is not None

    # Create manual swap between Alex(1) and Sam(2) for current week.
    swap = client.post(
        "/v1/cleaning/overrides/swap",
        headers=auth_headers,
        json={
            "week_start": week_start.isoformat(),
            "member_a_id": 1,
            "member_b_id": 2,
            "actor_user_id": "u1",
            "cancel": False,
        },
    )
    assert swap.status_code == 200
    notifications = swap.json()["notifications"]
    assert len(notifications) == 2

    schedule = client.get("/v1/cleaning/schedule?weeks_ahead=4", headers=auth_headers)
    assert schedule.status_code == 200
    rows = schedule.json()["schedule"]
    assert rows[0]["week_start"] == week_start.isoformat()

    # Mark takeover done: Sam cleaned Alex's shift.
    takeover = client.post(
        "/v1/cleaning/mark_takeover_done",
        headers=auth_headers,
        json={
            "week_start": week_start.isoformat(),
            "original_assignee_member_id": 1,
            "cleaner_member_id": 2,
            "actor_user_id": "u2",
        },
    )
    assert takeover.status_code == 200
    takeover_notifications = takeover.json()["notifications"]
    assert len(takeover_notifications) == 2

    schedule_after = client.get("/v1/cleaning/schedule?weeks_ahead=6", headers=auth_headers)
    assert schedule_after.status_code == 200
    rows_after = schedule_after.json()["schedule"]

    row_map = {date.fromisoformat(r["week_start"]): r for r in rows_after}
    compensation_rows = [
        row for row in row_map.values() if row["override_type"] == "compensation"
    ]
    assert compensation_rows, "Expected a compensation override to be created"
    compensation_row = compensation_rows[0]
    assert compensation_row["baseline_assignee_member_id"] == 2
    assert compensation_row["effective_assignee_member_id"] == 1


def test_due_notifications_schedule(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    # Monday assignment notification should fire with warning when previous week is unconfirmed.
    monday_due = client.get(
        "/v1/cleaning/notifications/due",
        headers=auth_headers,
        params={"at": _iso_at(week_start, 11, 0)},
    )
    assert monday_due.status_code == 200
    monday_notifications = monday_due.json()["notifications"]
    assert len(monday_notifications) == 1
    assert "Warning:" in monday_notifications[0]["message"]

    # Sunday reminders fire if still pending.
    sunday = week_start + timedelta(days=6)
    sunday_18 = client.get(
        "/v1/cleaning/notifications/due",
        headers=auth_headers,
        params={"at": _iso_at(sunday, 18, 0)},
    )
    assert sunday_18.status_code == 200
    assert len(sunday_18.json()["notifications"]) == 1

    sunday_21 = client.get(
        "/v1/cleaning/notifications/due",
        headers=auth_headers,
        params={"at": _iso_at(sunday, 21, 0)},
    )
    assert sunday_21.status_code == 200
    assert len(sunday_21.json()["notifications"]) == 1


def test_sunday_reminders_suppressed_after_completion(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    done = client.post(
        "/v1/cleaning/mark_done",
        headers=auth_headers,
        json={"week_start": week_start.isoformat(), "actor_user_id": "u1"},
    )
    assert done.status_code == 200

    sunday = week_start + timedelta(days=6)
    sunday_18 = client.get(
        "/v1/cleaning/notifications/due",
        headers=auth_headers,
        params={"at": _iso_at(sunday, 18, 0)},
    )
    assert sunday_18.status_code == 200
    assert sunday_18.json()["notifications"] == []


def test_compensation_conflict_moves_to_next_eligible_week(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])

    baseline_schedule = client.get("/v1/cleaning/schedule?weeks_ahead=20", headers=auth_headers)
    assert baseline_schedule.status_code == 200
    rows = baseline_schedule.json()["schedule"]
    cleaner_weeks = [
        date.fromisoformat(row["week_start"])
        for row in rows
        if date.fromisoformat(row["week_start"]) > week_start and row["baseline_assignee_member_id"] == 2
    ]
    assert len(cleaner_weeks) >= 2
    blocked_week = cleaner_weeks[0]
    expected_compensation_week = cleaner_weeks[1]

    # Pre-fill the cleaner's first eligible baseline week with a manual swap.
    blocked = client.post(
        "/v1/cleaning/overrides/swap",
        headers=auth_headers,
        json={
            "week_start": blocked_week.isoformat(),
            "member_a_id": 2,
            "member_b_id": 3,
            "actor_user_id": "u1",
            "cancel": False,
        },
    )
    assert blocked.status_code == 200

    takeover = client.post(
        "/v1/cleaning/mark_takeover_done",
        headers=auth_headers,
        json={
            "week_start": week_start.isoformat(),
            "original_assignee_member_id": 1,
            "cleaner_member_id": 2,
            "actor_user_id": "u2",
        },
    )
    assert takeover.status_code == 200

    schedule = client.get("/v1/cleaning/schedule?weeks_ahead=8", headers=auth_headers)
    assert schedule.status_code == 200
    row_map = {date.fromisoformat(row["week_start"]): row for row in schedule.json()["schedule"]}

    assert row_map[expected_compensation_week]["override_type"] == "compensation"


def test_week_start_must_be_monday(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])
    invalid_day = week_start + timedelta(days=1)

    response = client.post(
        "/v1/cleaning/mark_done",
        headers=auth_headers,
        json={"week_start": invalid_day.isoformat(), "actor_user_id": "u1"},
    )
    assert response.status_code == 400
