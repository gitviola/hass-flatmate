"""Fair "who buys next" order in GET /v1/stats/buys."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import update


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


def _setup(client, headers, purchases: list[tuple[int, str]]) -> None:
    members = [
        {"display_name": name, "ha_user_id": f"u-{name}", "ha_person_entity_id": f"person.{name.lower()}"}
        for name in ("Andy", "Carolina", "Martin", "Michelle")
    ]
    assert client.put("/v1/members/sync", headers=headers, json={"members": members}).status_code == 200
    # Founding members came from the first sync long ago; Carolina joined a week ago.
    for name in ("Andy", "Martin", "Michelle"):
        _set_created_days_ago(name, 200)
    _set_created_days_ago("Carolina", 7)

    if not purchases:
        return
    today = date.today()
    rows = "\n".join(f"{(today - timedelta(days=days)).isoformat()},Item,{name}" for days, name in purchases)
    response = client.post("/v1/import/manual", headers=headers, json={"shopping_history_rows": rows})
    assert response.status_code == 200, response.text


def _stats(client, headers) -> dict:
    response = client.get("/v1/stats/buys", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _order(client, headers) -> list[dict]:
    return _stats(client, headers)["buy_order"]


def test_new_member_is_not_pushed_to_front(client, auth_headers) -> None:
    purchases = (
        [(10 + i, "Andy") for i in range(3)]
        + [(10 + i, "Martin") for i in range(5)]
        + [(10 + i, "Michelle") for i in range(6)]
    )
    _setup(client, auth_headers, purchases)

    order = _order(client, auth_headers)
    assert [row["name"] for row in order] == ["Andy", "Carolina", "Martin", "Michelle"]

    andy, carolina = order[0], order[1]
    # 14 purchases over 3x90 + 7 present days
    assert andy["fair_share"] == round(14 * 90 / 277, 2)
    assert carolina["fair_share"] == round(14 * 7 / 277, 2)
    assert carolina["new_member"] is True and carolina["days_present"] == 7
    assert andy["new_member"] is False and andy["moved_in_at"] is None
    assert andy["person_entity_id"] == "person.andy"

    assert carolina["reason"].startswith("Moved in 7 days ago: 0 bought in 90 days")
    assert _stats(client, auth_headers)["buy_order_note"] == "Carolina only moved in 7 days ago."
    assert [row["recommendation"] for row in order] == ["Buy next", "Buy next", "", "Thanks!"]


def test_newcomer_who_is_not_recommended_is_labelled(client, auth_headers) -> None:
    _setup(client, auth_headers, [(10, "Martin")] + [(10, "Michelle")] * 6)

    order = _order(client, auth_headers)
    assert [(row["name"], row["recommendation"]) for row in order] == [
        ("Andy", "Buy next"),
        ("Martin", "Buy next"),
        ("Carolina", "Just moved in"),
        ("Michelle", "Thanks!"),
    ]


def test_distribution_puts_the_more_pressing_buyer_lower_on_equal_counts(client, auth_headers) -> None:
    # Martin bought most recently, so of the two with 2 purchases Andy is more pressing.
    purchases = [(30, "Andy"), (20, "Andy"), (10, "Martin"), (1, "Martin"), (5, "Michelle")]
    _setup(client, auth_headers, purchases)

    stats = _stats(client, auth_headers)
    andy_rank = next(row["rank"] for row in stats["buy_order"] if row["name"] == "Andy")
    martin_rank = next(row["rank"] for row in stats["buy_order"] if row["name"] == "Martin")
    assert andy_rank < martin_rank
    assert [row["name"] for row in stats["distribution"]] == ["Martin", "Andy", "Michelle", "Carolina"]


def test_new_member_who_is_behind_goes_first(client, auth_headers) -> None:
    # Everyone else bought several times since Carolina arrived; she hasn't.
    purchases = [(5, "Andy")] * 9 + [(5, "Martin")] * 10 + [(5, "Michelle")] * 11
    _setup(client, auth_headers, purchases)

    stats = _stats(client, auth_headers)
    assert stats["buy_order"][0]["name"] == "Carolina"
    assert stats["buy_order"][0]["balance"] < 0
    assert stats["buy_order_note"] == ""


def test_catch_up_beyond_the_recommended_pair(client, auth_headers) -> None:
    _setup(client, auth_headers, [(10, "Michelle")] * 9)
    _set_created_days_ago("Carolina", 200)

    order = _order(client, auth_headers)
    # 9 purchases, 2.25 each: three are 2.25 behind, but only two can be "Buy next"
    assert [row["recommendation"] for row in order] == ["Buy next", "Buy next", "Catch up", "Thanks!"]


def test_tie_goes_to_whoever_bought_longer_ago(client, auth_headers) -> None:
    purchases = [(30, "Andy"), (2, "Martin"), (20, "Michelle"), (3, "Carolina")]
    _setup(client, auth_headers, purchases)
    _set_created_days_ago("Carolina", 200)  # everyone founding: equal shares

    stats = _stats(client, auth_headers)
    assert [row["name"] for row in stats["buy_order"]] == ["Andy", "Michelle", "Carolina", "Martin"]
    assert stats["buy_order_note"] == (
        "Andy, Michelle, Carolina and Martin have the same amount, so whoever bought longest ago goes first."
    )


def test_two_way_tie_names_who_bought_longer_ago(client, auth_headers) -> None:
    purchases = [(30, "Andy"), (10, "Martin"), (12, "Martin"), (5, "Michelle"), (6, "Michelle")]
    _setup(client, auth_headers, purchases)
    _set_created_days_ago("Carolina", 200)  # everyone founding: equal shares

    stats = _stats(client, auth_headers)
    assert [row["name"] for row in stats["buy_order"]] == ["Carolina", "Andy", "Martin", "Michelle"]
    assert stats["buy_order_note"] == ""

    client.post("/v1/import/manual", headers=auth_headers, json={"shopping_history_rows": f"{(date.today() - timedelta(days=40)).isoformat()},Item,Carolina"})
    stats = _stats(client, auth_headers)
    assert [row["name"] for row in stats["buy_order"][:3]] == ["Carolina", "Andy", "Martin"]
    assert stats["buy_order_note"] == "Carolina's last purchase was longer ago than Andy's."


def test_several_newcomers_are_summarised(client, auth_headers) -> None:
    _setup(client, auth_headers, [(10, "Andy")] + [(10, "Martin")] * 10)
    _set_created_days_ago("Michelle", 20)

    stats = _stats(client, auth_headers)
    assert [row["name"] for row in stats["buy_order"]] == ["Andy", "Michelle", "Carolina", "Martin"]
    assert stats["buy_order_note"] == "Michelle and Carolina only moved in recently."


def test_newcomer_note_uses_weeks(client, auth_headers) -> None:
    _setup(client, auth_headers, [(10, "Andy"), (10, "Martin"), (11, "Martin")] + [(10, "Michelle")] * 3)
    _set_created_days_ago("Carolina", 21)
    assert _stats(client, auth_headers)["buy_order_note"] == "Carolina only moved in 3 weeks ago."


def test_members_expose_move_in(client, auth_headers) -> None:
    _setup(client, auth_headers, [])
    members = {row["display_name"]: row for row in client.get("/v1/members", headers=auth_headers).json()}
    assert members["Andy"]["moved_in_at"] is None
    assert members["Andy"]["created_at"] is not None
    assert members["Carolina"]["moved_in_at"] is not None


def test_empty_history_has_an_order(client, auth_headers) -> None:
    _setup(client, auth_headers, [])
    order = _order(client, auth_headers)
    assert len(order) == 4
    assert all(row["balance"] == 0 for row in order)
