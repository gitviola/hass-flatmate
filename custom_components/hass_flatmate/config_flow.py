"""Config flow for hass_flatmate integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_TOKEN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HassFlatmateApiClient, HassFlatmateApiError
from .const import CONF_BASE_URL, CONF_SCAN_INTERVAL, DEFAULT_BASE_URL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .discovery import async_discover_service_base_url


class HassFlatmateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for hass_flatmate."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        discovered_base_url = await async_discover_service_base_url(self.hass)
        suggested_base_url = discovered_base_url or DEFAULT_BASE_URL

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_BASE_URL].strip().lower())
            self._abort_if_unique_id_configured()

            api = HassFlatmateApiClient(
                async_get_clientsession(self.hass),
                user_input[CONF_BASE_URL],
                user_input[CONF_API_TOKEN],
            )
            try:
                await api.health()
            except HassFlatmateApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Hass Flatmate",
                    data={
                        CONF_BASE_URL: user_input[CONF_BASE_URL],
                        CONF_API_TOKEN: user_input[CONF_API_TOKEN],
                    },
                    options={
                        CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BASE_URL,
                        default=user_input[CONF_BASE_URL] if user_input else suggested_base_url,
                    ): str,
                    vol.Required(CONF_API_TOKEN): str,
                    vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=600)
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return HassFlatmateOptionsFlow(config_entry)


class HassFlatmateOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow updates."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
                }
            ),
        )
