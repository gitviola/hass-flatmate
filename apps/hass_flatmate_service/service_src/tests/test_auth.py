"""Authentication behavior tests."""

from __future__ import annotations


def test_missing_token_is_rejected(client) -> None:
    response = client.get("/v1/members")
    assert response.status_code == 401


def test_invalid_token_is_rejected(client) -> None:
    response = client.get("/v1/members", headers={"x-flatmate-token": "wrong"})
    assert response.status_code == 401
