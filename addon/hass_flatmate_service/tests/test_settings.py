"""Settings resolution tests."""

from __future__ import annotations

from pathlib import Path

from app import settings as settings_module


def test_db_path_prefers_explicit_env(monkeypatch) -> None:
    monkeypatch.setenv("HASS_FLATMATE_DB_PATH", "/tmp/custom-flatmate.db")
    settings = settings_module.Settings()
    assert settings.db_path == Path("/tmp/custom-flatmate.db")


def test_db_path_defaults_to_ha_config_mount(monkeypatch) -> None:
    monkeypatch.delenv("HASS_FLATMATE_DB_PATH", raising=False)
    monkeypatch.setattr(settings_module, "_ha_config_mount_exists", lambda: True)

    settings = settings_module.Settings()
    assert settings.db_path == Path("/config/hass_flatmate_service/hass_flatmate.db")


def test_db_path_defaults_to_local_data_when_not_in_ha(monkeypatch) -> None:
    monkeypatch.delenv("HASS_FLATMATE_DB_PATH", raising=False)
    monkeypatch.setattr(settings_module, "_ha_config_mount_exists", lambda: False)

    settings = settings_module.Settings()
    assert settings.db_path == Path("./data/hass_flatmate.db")
