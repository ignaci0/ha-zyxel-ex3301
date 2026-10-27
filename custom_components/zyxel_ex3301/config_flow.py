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
    CONF_TRACK_NEW_DEVICES,
    CONF_TRACKED_DEVICES,
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


def _format_device_label(mac: str, hostname: str | None, ip: str | None) -> str:
    """Format device label with MAC address in braces for clarity."""
    name = hostname if (hostname and hostname != "Unknown") else "Unknown"
    label = f"{name} ({mac})"
    if ip:
        label += f" - {ip}"
    return label


class ZyxelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Zyxel EX3301-T0 (Digi)."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow state."""
        self._init_data: dict[str, Any] = {}
        self._discovered_hosts: list[dict[str, Any]] = []
        self._router_model: str = "EX3301-T0"

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
                self._router_model = api.model
                self._discovered_hosts = await api.async_get_lanhosts()
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
                self._init_data = {
                    CONF_HOST: host,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_SCAN_INTERVAL: scan_interval,
                }
                return await self.async_step_devices()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow user to select which discovered devices to whitelist and track."""
        device_options: dict[str, str] = {}
        default_selected: list[str] = []

        for host in self._discovered_hosts:
            mac = host.get("PhysAddress", "").lower().strip()
            if not mac:
                continue
            name = host.get("HostName")
            ip = host.get("IPAddress", "")
            device_options[mac] = _format_device_label(mac, name, ip)
            if host.get("Active"):
                default_selected.append(mac)

        # If no active devices detected, select all by default
        if not default_selected:
            default_selected = list(device_options.keys())

        if user_input is not None:
            selected_devices = user_input.get(CONF_TRACKED_DEVICES, [])
            track_new = user_input.get(CONF_TRACK_NEW_DEVICES, False)
            host = self._init_data[CONF_HOST]
            title = f"Zyxel {self._router_model} ({host})"

            return self.async_create_entry(
                title=title,
                data={
                    CONF_HOST: host,
                    CONF_USERNAME: self._init_data[CONF_USERNAME],
                    CONF_PASSWORD: self._init_data[CONF_PASSWORD],
                },
                options={
                    CONF_SCAN_INTERVAL: self._init_data[CONF_SCAN_INTERVAL],
                    CONF_CONSIDER_HOME: DEFAULT_CONSIDER_HOME,
                    CONF_TRACKED_DEVICES: selected_devices,
                    CONF_TRACK_NEW_DEVICES: track_new,
                },
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TRACKED_DEVICES, default=default_selected
                ): cv.multi_select(device_options),
                vol.Optional(CONF_TRACK_NEW_DEVICES, default=False): cv.boolean,
            }
        )

        return self.async_show_form(
            step_id="devices",
            data_schema=schema,
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
        """Manage the options and device whitelist."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        scan_interval = options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        consider_home = options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
        track_new_devices = options.get(CONF_TRACK_NEW_DEVICES, False)
        current_tracked = options.get(CONF_TRACKED_DEVICES, [])

        # Fetch known devices from coordinator data
        coordinator = self.hass.data.get(DOMAIN, {}).get(
            self._config_entry.entry_id, {}
        ).get("coordinator")

        device_options: dict[str, str] = {}
        if coordinator and coordinator.data:
            for mac, d in coordinator.data.items():
                name = d.get("hostname")
                ip = d.get("ip", "")
                device_options[mac] = _format_device_label(mac, name, ip)

        # Include previously tracked macs even if currently absent from router cache
        for mac in current_tracked:
            if mac not in device_options:
                device_options[mac] = _format_device_label(mac, "Unknown", None)

        # Make sure default only includes valid macs from device_options
        valid_defaults = [m for m in current_tracked if m in device_options]

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TRACKED_DEVICES, default=valid_defaults
                ): cv.multi_select(device_options),
                vol.Optional(CONF_TRACK_NEW_DEVICES, default=track_new_devices): cv.boolean,
                vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=300)
                ),
                vol.Optional(CONF_CONSIDER_HOME, default=consider_home): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1800)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
