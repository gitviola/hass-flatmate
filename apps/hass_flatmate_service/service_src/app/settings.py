"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Runtime settings for the service."""

    @property
    def db_path(self) -> Path:
        return Path(os.environ.get("HASS_FLATMATE_DB_PATH", "./data/hass_flatmate.db"))

    @property
    def api_token(self) -> str:
        return os.environ.get("HASS_FLATMATE_API_TOKEN", "dev-token")

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
