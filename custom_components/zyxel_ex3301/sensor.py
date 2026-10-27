"""Sensor platform for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZyxelDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for Zyxel EX3301-T0."""
    coordinator: ZyxelDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities = [
        ZyxelActiveDevicesSensor(coordinator, entry),
        ZyxelTotalDevicesSensor(coordinator, entry),
    ]
    async_add_entities(entities)


class ZyxelBaseSensor(CoordinatorEntity[ZyxelDataUpdateCoordinator], SensorEntity):
    """Base sensor for Zyxel router metrics."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info for the router itself."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Zyxel {self.coordinator.api.model} ({self._entry.data.get('host', 'Router')})",
            manufacturer="Zyxel (Digi)",
            model=self.coordinator.api.model,
            configuration_url=self.coordinator.api.base_url,
        )


class ZyxelActiveDevicesSensor(ZyxelBaseSensor):
    """Sensor showing count of currently active/connected devices."""

    _attr_translation_key = "active_devices"
    _attr_icon = "mdi:devices"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize active devices sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_active_devices"

    @property
    def native_value(self) -> int:
        """Return the number of active devices."""
        if not self.coordinator.data:
            return 0
        return sum(1 for d in self.coordinator.data.values() if d.get("is_connected"))


class ZyxelTotalDevicesSensor(ZyxelBaseSensor):
    """Sensor showing total number of known devices in DHCP/hosts table."""

    _attr_translation_key = "total_devices"
    _attr_icon = "mdi:router-network"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize total devices sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_total_devices"

    @property
    def native_value(self) -> int:
        """Return the number of total known devices."""
        if not self.coordinator.data:
            return 0
        return len(self.coordinator.data)
