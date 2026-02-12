"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


def _ha_config_mount_exists() -> bool:
    return Path("/config").exists()


def _default_db_path() -> Path:
    if _ha_config_mount_exists():
        return Path("/config/hass_flatmate_service/hass_flatmate.db")
    return Path("./data/hass_flatmate.db")


class Settings:
    """Runtime settings for the service."""

    @property
    def db_path(self) -> Path:
        configured = os.environ.get("HASS_FLATMATE_DB_PATH")
        if configured:
            return Path(configured)
        return _default_db_path()

    @property
    def api_token(self) -> str:
        return os.environ.get("HASS_FLATMATE_API_TOKEN", "dev-token")

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
