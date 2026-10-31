"""Button platform for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
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
    """Set up buttons for Zyxel EX3301-T0."""
    coordinator: ZyxelDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([ZyxelRebootButton(coordinator, entry)])


class ZyxelRebootButton(CoordinatorEntity[ZyxelDataUpdateCoordinator], ButtonEntity):
    """Button to trigger router reboot."""

    _attr_has_entity_name = True
    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize reboot button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_reboot"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info linking this entity to the router device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
        )

    async def async_press(self) -> None:
        """Press the button to reboot the router."""
        _LOGGER.warning("Triggering reboot for Zyxel router at %s", self.coordinator.api.base_url)
        await self.coordinator.api.async_reboot()
