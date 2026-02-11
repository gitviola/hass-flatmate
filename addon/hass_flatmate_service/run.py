"""Run hass-flatmate service with uvicorn."""

from __future__ import annotations

import os

import uvicorn


if __name__ == "__main__":
    host = os.environ.get("HASS_FLATMATE_HOST", "0.0.0.0")
    port = int(os.environ.get("HASS_FLATMATE_PORT", "8099"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
