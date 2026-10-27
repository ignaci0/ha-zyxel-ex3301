"""Config flow and Options flow for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .api import ZyxelAuthError, ZyxelConnectionError, ZyxelRouterApi
from .const import (
    CONF_CONSIDER_HOME,
    CONF_ONLY_ACTIVE,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): cv.string,
        vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        ),
    }
)


class ZyxelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zyxel EX3301-T0 (Digi)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial user setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            # Prevent duplicate entries for the same host
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()

            api = ZyxelRouterApi(
                host=host,
                username=username,
                password=password,
                loop=self.hass.loop,
            )

            try:
                await api.async_login()
                await api.async_logout()
            except ZyxelAuthError:
                errors["base"] = "invalid_auth"
            except ZyxelConnectionError:
                errors["base"] = "cannot_connect"
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during Zyxel setup: %s", err)
                errors["base"] = "unknown"
            finally:
                await api.async_close()

            if not errors:
                title = f"Zyxel {api.model} ({host})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_SCAN_INTERVAL: scan_interval,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return ZyxelOptionsFlowHandler(config_entry)


class ZyxelOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Zyxel EX3301-T0 (Digi)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        scan_interval = options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        consider_home = options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
        only_active = options.get(CONF_ONLY_ACTIVE, False)

        options_schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
                vol.Optional(CONF_CONSIDER_HOME, default=consider_home): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1800)
                ),
                vol.Optional(CONF_ONLY_ACTIVE, default=only_active): cv.boolean,
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
