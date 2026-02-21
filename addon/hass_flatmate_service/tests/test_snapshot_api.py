"""Snapshot export/import API tests."""

from __future__ import annotations

from datetime import date


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


def test_snapshot_migration_ui_is_available(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Snapshot Migration" in response.text
    assert "Export snapshot" in response.text
    assert "Uses your configured add-on token automatically." in response.text
    assert "id=\"token\"" not in response.text
    assert "id=\"save-token\"" not in response.text
    assert 'fetch("v1/members"' in response.text
    assert 'fetch("v1/admin/export"' in response.text
    assert 'fetch("v1/admin/import"' in response.text


def test_snapshot_export_import_roundtrip(client, auth_headers) -> None:
    _sync_members(client, auth_headers)

    current = client.get("/v1/cleaning/current", headers=auth_headers)
    assert current.status_code == 200
    week_start = date.fromisoformat(current.json()["week_start"])
    member_a_id = int(current.json()["effective_assignee_member_id"])
    member_b_id = 2 if member_a_id != 2 else 3

    shopping_added = client.post(
        "/v1/shopping/items",
        headers=auth_headers,
        json={"name": "Milk", "actor_user_id": "u1"},
    )
    assert shopping_added.status_code == 200
    item_id = int(shopping_added.json()["id"])

    shopping_completed = client.post(
        f"/v1/shopping/items/{item_id}/complete",
        headers=auth_headers,
        json={"actor_user_id": "u1"},
    )
    assert shopping_completed.status_code == 200

    swap = client.post(
        "/v1/cleaning/overrides/swap",
        headers=auth_headers,
        json={
            "week_start": week_start.isoformat(),
            "member_a_id": member_a_id,
            "member_b_id": member_b_id,
            "actor_user_id": "u1",
            "cancel": False,
        },
    )
    assert swap.status_code == 200

    exported = client.get("/v1/admin/export", headers=auth_headers)
    assert exported.status_code == 200
    snapshot = exported.json()
    assert snapshot["schema_version"] == 1
    assert snapshot["summary"]["members"] == 3
    assert snapshot["summary"]["shopping_items"] >= 1
    assert snapshot["summary"]["cleaning_overrides"] >= 1

    reset = client.post("/v1/admin/reset", headers=auth_headers)
    assert reset.status_code == 200

    imported = client.post(
        "/v1/admin/import",
        headers=auth_headers,
        json={
            "snapshot": snapshot,
            "replace_existing": True,
        },
    )
    assert imported.status_code == 200
    summary = imported.json()["summary"]["summary"]
    assert summary["members"] == 3
    assert summary["shopping_items"] >= 1

    members = client.get("/v1/members", headers=auth_headers)
    assert members.status_code == 200
    assert len(members.json()) == 3

    shopping_items = client.get("/v1/shopping/items", headers=auth_headers)
    assert shopping_items.status_code == 200
    names = [row["name"] for row in shopping_items.json()]
    assert "Milk" in names

    schedule = client.get("/v1/cleaning/schedule?weeks_ahead=4", headers=auth_headers)
    assert schedule.status_code == 200
    row_map = {date.fromisoformat(row["week_start"]): row for row in schedule.json()["schedule"]}
    assert row_map[week_start]["override_type"] == "manual_swap"


def test_snapshot_import_rejects_unsupported_schema_version(client, auth_headers) -> None:
    response = client.post(
        "/v1/admin/import",
        headers=auth_headers,
        json={
            "snapshot": {
                "schema_version": 999,
                "data": {},
            },
            "replace_existing": True,
        },
    )
    assert response.status_code == 400


def test_member_device_mappings_are_persisted_and_roundtrip(client, auth_headers) -> None:
    payload = {
        "members": [
            {
                "display_name": "Alex",
                "ha_user_id": "u1",
                "ha_person_entity_id": "person.alex",
                "notify_service": "notify.mobile_app_alex_phone",
                "notify_services": [
                    "notify.mobile_app_alex_phone",
                    "notify.mobile_app_alex_tablet",
                ],
                "device_trackers": [
                    "device_tracker.alex_phone",
                    "device_tracker.alex_tablet",
                ],
                "active": True,
            }
        ]
    }
    response = client.put("/v1/members/sync", headers=auth_headers, json=payload)
    assert response.status_code == 200

    members = client.get("/v1/members", headers=auth_headers)
    assert members.status_code == 200
    row = members.json()[0]
    assert row["ha_person_entity_id"] == "person.alex"
    assert row["notify_services"] == [
        "notify.mobile_app_alex_phone",
        "notify.mobile_app_alex_tablet",
    ]
    assert row["device_trackers"] == [
        "device_tracker.alex_phone",
        "device_tracker.alex_tablet",
    ]

    exported = client.get("/v1/admin/export", headers=auth_headers)
    assert exported.status_code == 200
    exported_members = exported.json()["data"]["members"]
    assert exported_members[0]["notify_services"] == [
        "notify.mobile_app_alex_phone",
        "notify.mobile_app_alex_tablet",
    ]
    assert exported_members[0]["device_trackers"] == [
        "device_tracker.alex_phone",
        "device_tracker.alex_tablet",
    ]

    reset = client.post("/v1/admin/reset", headers=auth_headers)
    assert reset.status_code == 200

    imported = client.post(
        "/v1/admin/import",
        headers=auth_headers,
        json={"snapshot": exported.json(), "replace_existing": True},
    )
    assert imported.status_code == 200

    members_after = client.get("/v1/members", headers=auth_headers)
    assert members_after.status_code == 200
    restored = members_after.json()[0]
    assert restored["notify_services"] == [
        "notify.mobile_app_alex_phone",
        "notify.mobile_app_alex_tablet",
    ]
    assert restored["device_trackers"] == [
        "device_tracker.alex_phone",
        "device_tracker.alex_tablet",
    ]
