"""Helpers to discover the hass-flatmate app base URL inside Home Assistant."""

from __future__ import annotations

import logging
import os
from typing import Any

from aiohttp import ClientError, ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

APP_SLUG = "hass_flatmate_service"
APP_PORT = 8099
SUPERVISOR_ADDONS_URL = "http://supervisor/addons"

_LOGGER = logging.getLogger(__name__)


def _addon_matches_slug(addon: dict[str, Any]) -> bool:
    slug = addon.get("slug")
    if isinstance(slug, str) and slug == APP_SLUG:
        return True

    addon_id = addon.get("addon")
    if isinstance(addon_id, str) and addon_id.endswith(f"_{APP_SLUG}"):
        return True

    return False


def _addon_host_candidates(addon: dict[str, Any]) -> list[str]:
    hosts: list[str] = []

    addon_id = addon.get("addon")
    if isinstance(addon_id, str) and addon_id.endswith(f"_{APP_SLUG}"):
        hosts.append(addon_id.replace("_", "-"))

    repository = addon.get("repository")
    slug = addon.get("slug")
    if isinstance(repository, str) and isinstance(slug, str) and slug == APP_SLUG:
        hosts.append(f"{repository}_{slug}".replace("_", "-"))

    hostname = addon.get("hostname")
    if isinstance(hostname, str):
        hosts.append(hostname)

    deduped: list[str] = []
    for host in hosts:
        if host and host not in deduped:
            deduped.append(host)
    return deduped


def _extract_addons(payload: dict[str, Any]) -> list[dict[str, Any]]:
    addons = payload.get("addons")
    if isinstance(addons, list):
        return [item for item in addons if isinstance(item, dict)]

    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("addons")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]

    return []


async def _is_health_ok(session: ClientSession, base_url: str) -> bool:
    try:
        async with session.get(f"{base_url}/health", timeout=5) as response:
            return response.status == 200
    except ClientError:
        return False


async def async_discover_service_base_url(hass: HomeAssistant) -> str | None:
    """Discover reachable internal URL for the hass-flatmate app."""

    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if not supervisor_token:
        return None

    session = async_get_clientsession(hass)
    headers = {"Authorization": f"Bearer {supervisor_token}"}

    try:
        async with session.get(SUPERVISOR_ADDONS_URL, headers=headers, timeout=10) as response:
            if response.status >= 400:
                _LOGGER.debug("Supervisor addons query failed with status %s", response.status)
                return None
            payload = await response.json()
    except (ClientError, ValueError) as err:
        _LOGGER.debug("Unable to discover app URL from supervisor API: %s", err)
        return None

    addons = _extract_addons(payload if isinstance(payload, dict) else {})
    for addon in addons:
        if not _addon_matches_slug(addon):
            continue

        for host in _addon_host_candidates(addon):
            base_url = f"http://{host}:{APP_PORT}"
            if await _is_health_ok(session, base_url):
                return base_url

    return None

