"""Move-in / move-out dates and how former flatmates count in fair shares."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import update

NAMES = ("Andy", "Carolina", "Emilie", "Martin", "Michelle")


def _sync(client, headers, names=NAMES) -> dict[str, dict]:
    members = [{"display_name": name, "ha_user_id": f"u-{name}"} for name in names]
    response = client.put("/v1/members/sync", headers=headers, json={"members": members})
    assert response.status_code == 200, response.text
    return _members(client, headers)


def _members(client, headers) -> dict[str, dict]:
    return {row["display_name"]: row for row in client.get("/v1/members", headers=headers).json()}


def _set_created_days_ago(display_name: str, days: int) -> None:
    from app import db
    from app.models import Member
    from app.services.time_utils import now_utc

    with db.SessionLocal() as session:
        session.execute(
            update(Member)
            .where(Member.display_name == display_name)
            .values(created_at=now_utc() - timedelta(days=days))
        )
        session.commit()


def _import(client, headers, purchases: list[tuple[int, str]]) -> None:
    today = date.today()
    rows = "\n".join(f"{(today - timedelta(days=days)).isoformat()},Item,{name}" for days, name in purchases)
    response = client.post("/v1/import/manual", headers=headers, json={"shopping_history_rows": rows})
    assert response.status_code == 200, response.text


def _tenancy(client, headers, member_id: int, **fields):
    return client.put(f"/v1/members/{member_id}/tenancy", headers=headers, json=fields)


def _balances(client, headers) -> dict[str, tuple[float, float]]:
    order = client.get("/v1/stats/buys", headers=headers).json()["buy_order"]
    return {row["name"]: (row["fair_share"], row["balance"]) for row in order}


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch):
    from app.services import members

    state = {"now": datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(members, "now_utc", lambda: state["now"])

    def advance(**delta: float) -> datetime:
        state["now"] += timedelta(**delta)
        return state["now"]

    return advance


def test_removal_records_move_out_and_a_real_return_a_new_move_in(client, auth_headers, clock) -> None:
    _sync(client, auth_headers)
    left_at = clock(days=0)
    members = _sync(client, auth_headers, [name for name in NAMES if name != "Emilie"])
    assert members["Emilie"]["active"] is False
    assert members["Emilie"]["moved_out_at"].startswith(left_at.isoformat()[:19])

    # Back within a day: never really moved out, original move-in kept.
    clock(hours=3)
    members = _sync(client, auth_headers)
    assert members["Emilie"]["moved_out_at"] is None
    assert members["Emilie"]["moved_in_at"] is None

    _sync(client, auth_headers, [name for name in NAMES if name != "Emilie"])
    returned_at = clock(days=30)
    members = _sync(client, auth_headers)
    assert members["Emilie"]["moved_out_at"] is None
    assert members["Emilie"]["moved_in_at"].startswith(returned_at.isoformat()[:19])


def test_set_and_clear_tenancy_dates(client, auth_headers) -> None:
    members = _sync(client, auth_headers)
    emilie = members["Emilie"]["id"]

    rejected = _tenancy(client, auth_headers, emilie, moved_out_at="2026-10-01T00:00:00+02:00")
    assert rejected.status_code == 400
    assert "no longer active" in rejected.json()["detail"]

    members = _sync(client, auth_headers, [name for name in NAMES if name != "Emilie"])
    response = _tenancy(
        client,
        auth_headers,
        emilie,
        moved_in_at="2026-03-01T00:00:00+01:00",
        moved_out_at="2026-10-01T00:00:00+02:00",
    )
    assert response.status_code == 200, response.text
    assert response.json()["moved_in_at"] == "2026-02-28T23:00:00Z"
    assert response.json()["moved_out_at"] == "2026-09-30T22:00:00Z"

    # Only the fields sent change; null clears.
    response = _tenancy(client, auth_headers, emilie, moved_in_at=None)
    assert response.json()["moved_in_at"] is None
    assert response.json()["moved_out_at"] == "2026-09-30T22:00:00Z"

    backwards = _tenancy(client, auth_headers, emilie, moved_in_at="2026-11-01T00:00:00Z")
    assert backwards.status_code == 400
    assert _tenancy(client, auth_headers, 999, moved_in_at=None).status_code == 404

    events = client.get("/v1/activity", headers=auth_headers).json()
    assert any(event["action"] == "member_tenancy_updated" for event in events)


def test_moving_out_does_not_shift_anyone_elses_balance(client, auth_headers) -> None:
    _sync(client, auth_headers)
    for name in NAMES:
        _set_created_days_ago(name, 200)
    _set_created_days_ago("Carolina", 7)
    # Emilie carried the flat for a while, then everyone bought a bit since Carolina arrived.
    _import(client, auth_headers, [(30, "Emilie")] * 8 + [(30, "Andy")] + [(30, "Martin")] * 3)
    _import(client, auth_headers, [(3, "Martin")] * 2 + [(3, "Michelle")] * 3)

    before = _balances(client, auth_headers)
    assert before["Andy"] == (4.0, -3.0)  # 12 split between 4, plus 5 split between 5

    members = _sync(client, auth_headers, [name for name in NAMES if name != "Emilie"])
    after = _balances(client, auth_headers)
    assert "Emilie" not in after
    assert after == {name: value for name, value in before.items() if name != "Emilie"}

    # Without a known move-out date she is left out entirely, as before move-out dates existed.
    _tenancy(client, auth_headers, members["Emilie"]["id"], moved_out_at=None)
    assert _balances(client, auth_headers)["Andy"] == (2.58, -1.58)  # 4 split between 3, plus 5 between 4


def test_former_flatmate_counts_until_the_move_out_date(client, auth_headers) -> None:
    _sync(client, auth_headers)
    for name in NAMES:
        _set_created_days_ago(name, 200)
    _set_created_days_ago("Carolina", 10)
    members = _sync(client, auth_headers, [name for name in NAMES if name != "Emilie"])
    # Emilie moved out the day Carolina moved in.
    moved_out = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    assert _tenancy(client, auth_headers, members["Emilie"]["id"], moved_out_at=moved_out).status_code == 200

    _import(client, auth_headers, [(30, "Andy")] * 5)  # Andy, Emilie, Martin, Michelle: 1.25 each
    _import(client, auth_headers, [(5, "Martin")] * 4)  # Andy, Carolina, Martin, Michelle: 1 each

    balances = _balances(client, auth_headers)
    assert balances["Carolina"] == (1.0, -1.0)
    assert balances["Andy"] == (2.25, 2.75)
    assert balances["Michelle"] == (2.25, -2.25)


def test_snapshot_keeps_tenancy_dates(client, auth_headers) -> None:
    members = _sync(client, auth_headers)
    members = _sync(client, auth_headers, [name for name in NAMES if name != "Emilie"])
    _tenancy(client, auth_headers, members["Emilie"]["id"], moved_out_at="2026-10-01T00:00:00Z")

    exported = client.get("/v1/admin/export", headers=auth_headers)
    assert client.post("/v1/admin/reset", headers=auth_headers).status_code == 200
    imported = client.post(
        "/v1/admin/import",
        headers=auth_headers,
        json={"snapshot": exported.json(), "replace_existing": True},
    )
    assert imported.status_code == 200, imported.text
    assert _members(client, auth_headers)["Emilie"]["moved_out_at"] == "2026-10-01T00:00:00Z"
