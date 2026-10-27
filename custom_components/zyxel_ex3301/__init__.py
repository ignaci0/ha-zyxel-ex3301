"""Zyxel EX3301-T0 (Digi) integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import ZyxelRouterApi
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import ZyxelDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Zyxel EX3301-T0 from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    host = entry.data[CONF_HOST]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    api = ZyxelRouterApi(
        host=host,
        username=username,
        password=password,
        loop=hass.loop,
    )

    coordinator = ZyxelDataUpdateCoordinator(
        hass=hass,
        api=api,
        scan_interval=scan_interval,
        entry_id=entry.entry_id,
        options=entry.options,
    )

    # Perform initial data fetch
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.warning("Error unloading platforms for %s: %s", entry.title, err)
        unload_ok = True

    entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if entry_data and "api" in entry_data:
        api: ZyxelRouterApi = entry_data["api"]
        try:
            await api.async_logout()
        except Exception:
            pass
        try:
            await api.async_close()
        except Exception:
            pass

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    _LOGGER.info("Removed config entry for %s", entry.title)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are modified."""
    await hass.config_entries.async_reload(entry.entry_id)
