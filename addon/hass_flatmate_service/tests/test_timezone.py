"""Week boundaries follow Home Assistant's local time zone, not UTC."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

MADRID = {"x-flatmate-timezone": "Europe/Madrid"}


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    from app.services import cleaning

    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.delenv("HASS_FLATMATE_TIMEZONE", raising=False)
    state = {"now": datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(cleaning, "now_utc", lambda: state["now"])

    def set_now(*args: int) -> None:
        state["now"] = datetime(*args, tzinfo=timezone.utc)

    return set_now


def _sync_members(client, headers) -> None:
    payload = {
        "members": [
            {"display_name": "Alex", "ha_user_id": "u1", "notify_service": "notify.alex", "active": True},
            {"display_name": "Sam", "ha_user_id": "u2", "notify_service": "notify.sam", "active": True},
            {"display_name": "Pat", "ha_user_id": "u3", "notify_service": "notify.pat", "active": True},
        ]
    }
    assert client.put("/v1/members/sync", headers=headers, json=payload).status_code == 200


def _current(client, headers) -> dict:
    response = client.get("/v1/cleaning/current", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_new_week_starts_at_local_midnight_in_summer_time(client, auth_headers, clock) -> None:
    headers = {**auth_headers, **MADRID}
    _sync_members(client, headers)
    previous_assignee = _current(client, headers)["effective_assignee_member_id"]

    # Sunday 23:30 in Madrid (CEST, UTC+2): still the old week.
    clock(2026, 10, 11, 21, 30)
    assert _current(client, headers)["week_start"] == "2026-10-05"

    # Monday 00:30 in Madrid is still Sunday 22:30 in UTC.
    clock(2026, 10, 11, 22, 30)
    current = _current(client, headers)
    assert current["week_start"] == "2026-10-12"
    assert current["effective_assignee_member_id"] != previous_assignee

    schedule = client.get("/v1/cleaning/schedule?weeks_ahead=2&include_previous_weeks=1", headers=headers)
    assert [row["week_start"] for row in schedule.json()["schedule"]] == ["2026-10-05", "2026-10-12", "2026-10-19"]

    rotation = client.get("/v1/cleaning/rotation", headers=headers)
    assert rotation.json()["week_start"] == "2026-10-12"


def test_new_week_starts_at_local_midnight_in_winter_time(client, auth_headers, clock) -> None:
    headers = {**auth_headers, **MADRID}
    _sync_members(client, headers)

    # DST ended on 2026-10-25, Madrid is now UTC+1.
    clock(2026, 11, 1, 22, 30)  # Sunday 23:30 local
    assert _current(client, headers)["week_start"] == "2026-10-26"
    clock(2026, 11, 1, 23, 30)  # Monday 00:30 local
    assert _current(client, headers)["week_start"] == "2026-11-02"


def test_falls_back_to_tz_env_without_header(client, auth_headers, clock, monkeypatch) -> None:
    _sync_members(client, auth_headers)
    clock(2026, 10, 11, 22, 30)  # Monday 00:30 in Madrid

    assert _current(client, auth_headers)["week_start"] == "2026-10-05"
    monkeypatch.setenv("TZ", "Europe/Madrid")
    assert _current(client, auth_headers)["week_start"] == "2026-10-12"


def test_invalid_timezone_header_falls_back_to_utc(client, auth_headers, clock) -> None:
    headers = {**auth_headers, "x-flatmate-timezone": "Not/AZone"}
    _sync_members(client, headers)
    clock(2026, 10, 11, 22, 30)
    assert _current(client, headers)["week_start"] == "2026-10-05"


def test_notifications_fire_at_local_times_for_the_current_assignee(client, auth_headers, clock) -> None:
    headers = {**auth_headers, **MADRID}
    _sync_members(client, headers)

    clock(2026, 10, 11, 22, 30)  # Monday 00:30 local
    assignee = _current(client, headers)["effective_assignee_member_id"]

    def due(at: str) -> list[dict]:
        response = client.get("/v1/cleaning/notifications/due", headers=headers, params={"at": at})
        assert response.status_code == 200
        return response.json()["notifications"]

    # The integration sends HA-local times (dt_util.now()), with their UTC offset.
    assert due("2026-10-12T10:59:00+02:00") == []
    monday = due("2026-10-12T11:00:00+02:00")
    assert [(n["notification_slot"], n["member_id"], n["week_start"]) for n in monday] == [
        ("monday_11", assignee, "2026-10-12")
    ]

    for slot, at in (
        ("sunday_11", "2026-10-18T11:00:00+02:00"),
        ("sunday_18", "2026-10-18T18:00:00+02:00"),
        ("sunday_21", "2026-10-18T21:00:00+02:00"),
    ):
        reminders = due(at)
        assert [(n["notification_slot"], n["member_id"], n["week_start"]) for n in reminders] == [
            (slot, assignee, "2026-10-12")
        ]
