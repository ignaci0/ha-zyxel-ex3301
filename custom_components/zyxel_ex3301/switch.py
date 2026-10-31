"""Switch platform for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZyxelDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for Zyxel EX3301-T0."""
    coordinator: ZyxelDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ZyxelLedSwitch(coordinator, entry)])


class ZyxelLedSwitch(CoordinatorEntity[ZyxelDataUpdateCoordinator], SwitchEntity):
    """Switch to turn router LEDs on or off (Stealth Mode)."""

    _attr_has_entity_name = True
    _attr_translation_key = "led_switch"
    _attr_icon = "mdi:led-on"

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize LED switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_led_switch"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info linking this entity to the router device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
        )

    @property
    def is_on(self) -> bool:
        """Return true if LEDs are active (on)."""
        if not self.coordinator.data:
            return False
        return bool(self.coordinator.data.get("led_status", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn router LEDs on."""
        await self.coordinator.api.async_set_led_status(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn router LEDs off (stealth mode)."""
        await self.coordinator.api.async_set_led_status(False)
        await self.coordinator.async_request_refresh()
