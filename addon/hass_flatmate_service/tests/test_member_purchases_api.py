"""Per-member purchase history (GET /v1/shopping/members/{id}/purchases)."""

from __future__ import annotations

from datetime import date, timedelta


def _setup(client, headers) -> None:
    members = [
        {"display_name": "Alex", "ha_user_id": "u1", "active": True},
        {"display_name": "Sam", "ha_user_id": "u2", "active": True},
    ]
    assert client.put("/v1/members/sync", headers=headers, json={"members": members}).status_code == 200

    today = date.today()
    rows = "\n".join(
        [
            f"{(today - timedelta(days=400)).isoformat()},Rice,Alex",
            f"{(today - timedelta(days=120)).isoformat()},Soap,Alex",
            f"{(today - timedelta(days=30)).isoformat()},Coffee,Alex",
            f"{(today - timedelta(days=10)).isoformat()},Bread,Sam",
        ]
    )
    response = client.post("/v1/import/manual", headers=headers, json={"shopping_history_rows": rows})
    assert response.status_code == 200, response.text

    # a live purchase through the normal flow, plus one that stays open
    client.post("/v1/shopping/items", headers=headers, json={"name": "Milk", "actor_user_id": "u1"})
    client.post("/v1/shopping/items", headers=headers, json={"name": "Eggs", "actor_user_id": "u1"})
    items = client.get("/v1/shopping/items", headers=headers).json()
    milk = next(item for item in items if item["name"] == "Milk" and item["status"] == "open")
    assert client.post(
        f"/v1/shopping/items/{milk['id']}/complete", headers=headers, json={"actor_user_id": "u1"}
    ).status_code == 200


def test_history_covers_all_time_newest_first_with_window_flag(client, auth_headers) -> None:
    _setup(client, auth_headers)

    response = client.get("/v1/shopping/members/1/purchases", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()

    assert body["display_name"] == "Alex"
    assert body["window_days"] == 90
    assert [(p["name"], p["in_window"]) for p in body["purchases"]] == [
        ("Milk", True),
        ("Coffee", True),
        ("Soap", False),
        ("Rice", False),
    ]
    assert body["total_count"] == 4
    assert body["in_window_count"] == 2
    assert body["purchases"][0]["completed_at"].endswith(("Z", "+00:00"))


def test_in_window_count_matches_distribution(client, auth_headers) -> None:
    _setup(client, auth_headers)
    distribution = client.get("/v1/stats/buys?window_days=90", headers=auth_headers).json()["distribution"]
    for row in distribution:
        history = client.get(f"/v1/shopping/members/{row['member_id']}/purchases", headers=auth_headers).json()
        assert history["in_window_count"] == row["count"]


def test_unknown_member_is_404(client, auth_headers) -> None:
    _setup(client, auth_headers)
    assert client.get("/v1/shopping/members/999/purchases", headers=auth_headers).status_code == 404


def test_requires_token(client) -> None:
    assert client.get("/v1/shopping/members/1/purchases").status_code == 401
