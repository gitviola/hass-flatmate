"""Test fixtures for hass-flatmate service."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("HASS_FLATMATE_DB_PATH", str(db_path))
    monkeypatch.setenv("HASS_FLATMATE_API_TOKEN", "test-token")

    from app import db
    from app.db import Base
    from app.main import app

    db.configure_engine(f"sqlite:///{db_path}")
    assert db.engine is not None
    Base.metadata.drop_all(bind=db.engine)
    Base.metadata.create_all(bind=db.engine)

    with TestClient(app) as api_client:
        yield api_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"x-flatmate-token": "test-token"}
