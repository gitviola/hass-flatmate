"""Re-sending a logged cleaning notification (POST /v1/cleaning/notifications/resend)."""

from __future__ import annotations

from datetime import date


def _sync_members(client, headers, *, include_sam: bool = True) -> None:
    members = [
        {"display_name": "Alex", "ha_user_id": "u1", "notify_service": "notify.mobile_app_alex", "active": True},
        {"display_name": "Sam", "ha_user_id": "u2", "notify_service": "notify.mobile_app_sam", "active": True},
    ]
    if not include_sam:
        members = members[:1]
    response = client.put("/v1/members/sync", headers=headers, json={"members": members})
    assert response.status_code == 200


def _log_dispatch(client, headers, *, member_id: int, title: str | None = "Weekly Cleaning Shift") -> int:
    week_start = date.fromisoformat(client.get("/v1/cleaning/current", headers=headers).json()["week_start"])
    response = client.post(
        "/v1/cleaning/notifications/dispatch",
        headers=headers,
        json={
            "records": [
                {
                    "week_start": week_start.isoformat(),
                    "member_id": member_id,
                    "notify_service": "notify.mobile_app_sam",
                    "title": title,
                    "message": "It is your turn to clean the common areas this week.",
                    "notification_kind": "weekly_assignment",
                    "notification_slot": "monday_11",
                    "source_action": "cleaning_notifications_due",
                    "status": "sent",
                }
            ]
        },
    )
    assert response.status_code == 200
    activity = client.get("/v1/activity?limit=20", headers=headers).json()
    return next(row["id"] for row in activity if row["action"] == "cleaning_notification_dispatch")


def test_resend_returns_original_notification_and_logs_request(client, auth_headers) -> None:
    _sync_members(client, auth_headers)
    event_id = _log_dispatch(client, auth_headers, member_id=2)
    week_start = client.get("/v1/cleaning/current", headers=auth_headers).json()["week_start"]

    response = client.post(
        "/v1/cleaning/notifications/resend",
        headers=auth_headers,
        json={"dispatch_event_id": event_id},
    )
    assert response.status_code == 200
    notifications = response.json()["notifications"]
    assert notifications == [
        {
            "member_id": 2,
            "notify_service": "notify.mobile_app_sam",
            "title": "Weekly Cleaning Shift",
            "message": "It is your turn to clean the common areas this week.",
            "category": "cleaning",
            "week_start": week_start,
            "notification_kind": "weekly_assignment",
            "notification_slot": "monday_11",
            "source_action": "cleaning_notification_resend",
        }
    ]

    activity = client.get("/v1/activity?limit=20", headers=auth_headers).json()
    requested = next(row for row in activity if row["action"] == "cleaning_notification_resend_requested")
    assert requested["actor_member_id"] is None
    assert requested["actor_user_id_raw"] is None
    assert requested["payload_json"]["source_event_id"] == event_id


def test_resend_rejects_unknown_or_non_dispatch_events(client, auth_headers) -> None:
    _sync_members(client, auth_headers)
    assert client.post(
        "/v1/cleaning/notifications/resend", headers=auth_headers, json={"dispatch_event_id": 99999}
    ).status_code == 400

    current = client.get("/v1/cleaning/current", headers=auth_headers).json()
    client.post("/v1/cleaning/mark_done", headers=auth_headers, json={"week_start": current["week_start"]})
    activity = client.get("/v1/activity?limit=20", headers=auth_headers).json()
    done_event_id = next(row["id"] for row in activity if row["action"] == "cleaning_done")
    assert client.post(
        "/v1/cleaning/notifications/resend", headers=auth_headers, json={"dispatch_event_id": done_event_id}
    ).status_code == 400


def test_resend_rejects_inactive_recipient(client, auth_headers) -> None:
    _sync_members(client, auth_headers)
    event_id = _log_dispatch(client, auth_headers, member_id=2)
    _sync_members(client, auth_headers, include_sam=False)

    response = client.post(
        "/v1/cleaning/notifications/resend", headers=auth_headers, json={"dispatch_event_id": event_id}
    )
    assert response.status_code == 400
    assert "no longer active" in response.json()["detail"]


def test_resend_requires_token(client) -> None:
    assert client.post("/v1/cleaning/notifications/resend", json={"dispatch_event_id": 1}).status_code == 401
