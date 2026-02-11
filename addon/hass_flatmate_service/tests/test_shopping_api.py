"""Shopping API behavior tests."""

from __future__ import annotations


def _sync_members(client, headers) -> None:
    payload = {
        "members": [
            {
                "display_name": "Martin",
                "ha_user_id": "u1",
                "notify_service": "notify.mobile_app_martin",
                "active": True,
            },
            {
                "display_name": "Martina",
                "ha_user_id": "u2",
                "notify_service": "notify.mobile_app_martina",
                "active": True,
            },
            {
                "display_name": "Gianmarco",
                "ha_user_id": "u3",
                "notify_service": "notify.mobile_app_gian",
                "active": True,
            },
            {
                "display_name": "Maria",
                "ha_user_id": "u4",
                "notify_service": "notify.mobile_app_maria",
                "active": True,
            },
        ]
    }
    response = client.put("/v1/members/sync", headers=headers, json=payload)
    assert response.status_code == 200


def test_shopping_lifecycle_and_stats(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    add_rice = client.post(
        "/v1/shopping/items",
        headers=auth_headers,
        json={"name": "Rice", "actor_user_id": "u1"},
    )
    assert add_rice.status_code == 200
    rice_id = add_rice.json()["id"]

    add_pasta = client.post(
        "/v1/shopping/items",
        headers=auth_headers,
        json={"name": "Pasta", "actor_user_id": "u2"},
    )
    assert add_pasta.status_code == 200
    pasta_id = add_pasta.json()["id"]

    add_unknown = client.post(
        "/v1/shopping/items",
        headers=auth_headers,
        json={"name": "Soap", "actor_user_id": "u_unknown"},
    )
    assert add_unknown.status_code == 200
    unknown_id = add_unknown.json()["id"]

    complete_rice = client.post(
        f"/v1/shopping/items/{rice_id}/complete",
        headers=auth_headers,
        json={"actor_user_id": "u1"},
    )
    assert complete_rice.status_code == 200

    complete_rice_again = client.post(
        f"/v1/shopping/items/{rice_id}/complete",
        headers=auth_headers,
        json={"actor_user_id": "u1"},
    )
    assert complete_rice_again.status_code == 200

    complete_unknown = client.post(
        f"/v1/shopping/items/{unknown_id}/complete",
        headers=auth_headers,
        json={"actor_user_id": "u_unknown"},
    )
    assert complete_unknown.status_code == 200

    delete_pasta = client.request(
        "DELETE",
        f"/v1/shopping/items/{pasta_id}",
        headers=auth_headers,
        json={"actor_user_id": "u2"},
    )
    assert delete_pasta.status_code == 200

    delete_pasta_again = client.request(
        "DELETE",
        f"/v1/shopping/items/{pasta_id}",
        headers=auth_headers,
        json={"actor_user_id": "u2"},
    )
    assert delete_pasta_again.status_code == 200

    stats = client.get("/v1/stats/buys?window_days=90", headers=auth_headers)
    assert stats.status_code == 200
    payload = stats.json()

    assert payload["window_days"] == 90
    assert payload["total_completed"] == 2
    assert payload["unknown_excluded_count"] == 1

    distribution = payload["distribution"]
    names = [row["name"] for row in distribution]
    assert names == ["Martin", "Gianmarco", "Maria", "Martina"]

    by_name = {row["name"]: row for row in distribution}
    assert by_name["Martin"]["count"] == 1
    assert by_name["Martina"]["count"] == 0
    assert by_name["Gianmarco"]["count"] == 0
    assert by_name["Maria"]["count"] == 0

    open_items = client.get("/v1/shopping/items", headers=auth_headers)
    assert open_items.status_code == 200
    statuses = {item["name"]: item["status"] for item in open_items.json()}
    assert statuses["Rice"] == "completed"
    assert statuses["Soap"] == "completed"
    assert statuses["Pasta"] == "deleted"

    activity = client.get("/v1/activity?limit=20", headers=auth_headers)
    assert activity.status_code == 200
    actions = [event["action"] for event in activity.json()]
    assert "shopping_item_added" in actions
    assert "shopping_item_completed" in actions
    assert "shopping_item_deleted" in actions


def test_recents_and_favorites(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    for name in ["Milk", "Bread", "Milk", "Eggs"]:
        response = client.post(
            "/v1/shopping/items",
            headers=auth_headers,
            json={"name": name, "actor_user_id": "u1"},
        )
        assert response.status_code == 200

    recents = client.get("/v1/shopping/recents?limit=3", headers=auth_headers)
    assert recents.status_code == 200
    assert recents.json()["recents"] == ["Eggs", "Milk", "Bread"]

    add_favorite = client.post(
        "/v1/shopping/favorites",
        headers=auth_headers,
        json={"name": "Pasta", "actor_user_id": "u1"},
    )
    assert add_favorite.status_code == 200
    favorite_id = add_favorite.json()["id"]

    favorites = client.get("/v1/shopping/favorites", headers=auth_headers)
    assert favorites.status_code == 200
    assert len(favorites.json()["favorites"]) == 1

    delete_favorite = client.request(
        "DELETE",
        f"/v1/shopping/favorites/{favorite_id}",
        headers=auth_headers,
        json={"actor_user_id": "u1"},
    )
    assert delete_favorite.status_code == 200

    favorites_after = client.get("/v1/shopping/favorites", headers=auth_headers)
    assert favorites_after.status_code == 200
    assert favorites_after.json()["favorites"] == []


def test_distribution_svg_endpoint(client, auth_headers) -> None:
    _sync_members(client, auth_headers)
    add_response = client.post(
        "/v1/shopping/items",
        headers=auth_headers,
        json={"name": "Dish Soap", "actor_user_id": "u1"},
    )
    assert add_response.status_code == 200
    item_id = add_response.json()["id"]
    complete_response = client.post(
        f"/v1/shopping/items/{item_id}/complete",
        headers=auth_headers,
        json={"actor_user_id": "u1"},
    )
    assert complete_response.status_code == 200

    response = client.get("/v1/stats/buys.svg?window_days=90", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in response.text
    assert "Martin" in response.text
    assert "Martina" in response.text
    assert "Gianmarco" in response.text
    assert "Maria" in response.text
