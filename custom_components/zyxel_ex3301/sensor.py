"""Sensor platform for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import ZyxelDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for Zyxel EX3301-T0."""
    coordinator: ZyxelDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[SensorEntity] = [
        ZyxelActiveDevicesSensor(coordinator, entry),
        ZyxelTotalDevicesSensor(coordinator, entry),
        ZyxelCpuSensor(coordinator, entry),
        ZyxelMemorySensor(coordinator, entry),
        ZyxelUptimeSensor(coordinator, entry),
        ZyxelWanIpSensor(coordinator, entry),
        ZyxelWanIpv6Sensor(coordinator, entry),
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
        """Return the device info linking this entity to the router device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
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
        devices = self.coordinator.data.get("devices", {})
        return sum(1 for d in devices.values() if d.get("is_connected"))


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
        devices = self.coordinator.data.get("devices", {})
        return len(devices)


class ZyxelCpuSensor(ZyxelBaseSensor):
    """Sensor showing router CPU utilization percentage."""

    _attr_translation_key = "cpu_usage"
    _attr_icon = "mdi:cpu-64-bit"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize CPU sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_cpu_usage"

    @property
    def native_value(self) -> int | None:
        """Return CPU usage percentage."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("system", {}).get("cpu_usage")


class ZyxelMemorySensor(ZyxelBaseSensor):
    """Sensor showing router RAM utilization percentage."""

    _attr_translation_key = "memory_usage"
    _attr_icon = "mdi:memory"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize memory sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_memory_usage"

    @property
    def native_value(self) -> float | None:
        """Return RAM usage percentage."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("system", {}).get("memory_usage")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed memory stats."""
        if not self.coordinator.data:
            return {}
        system = self.coordinator.data.get("system", {})
        return {
            "total_memory_kb": system.get("total_memory_kb", 0),
            "free_memory_kb": system.get("free_memory_kb", 0),
        }


class ZyxelUptimeSensor(ZyxelBaseSensor):
    """Sensor showing router boot timestamp / uptime."""

    _attr_translation_key = "uptime"
    _attr_icon = "mdi:clock-start"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize uptime sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_uptime"

    @property
    def native_value(self) -> datetime | None:
        """Return router start time as UTC datetime."""
        if not self.coordinator.data:
            return None
        uptime_seconds = self.coordinator.data.get("system", {}).get("uptime", 0)
        if not uptime_seconds:
            return None
        return dt_util.utcnow() - timedelta(seconds=uptime_seconds)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return uptime in seconds."""
        if not self.coordinator.data:
            return {}
        return {
            "uptime_seconds": self.coordinator.data.get("system", {}).get("uptime", 0),
        }


class ZyxelWanIpSensor(ZyxelBaseSensor):
    """Sensor displaying public WAN IPv4 address."""

    _attr_translation_key = "wan_ip"
    _attr_icon = "mdi:ip-network"

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize WAN IP sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_wan_ip"

    @property
    def native_value(self) -> str | None:
        """Return WAN IPv4 address."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("wan", {}).get("ip") or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return WAN gateway and DNS attributes."""
        if not self.coordinator.data:
            return {}
        wan = self.coordinator.data.get("wan", {})
        return {
            "gateway": wan.get("gateway", ""),
            "dns": wan.get("dns", ""),
            "interface_name": wan.get("name", "ETHWAN"),
        }


class ZyxelWanIpv6Sensor(ZyxelBaseSensor):
    """Sensor displaying WAN IPv6 address."""

    _attr_translation_key = "wan_ipv6"
    _attr_icon = "mdi:ip-network-outline"

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize WAN IPv6 sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_wan_ipv6"

    @property
    def native_value(self) -> str | None:
        """Return WAN IPv6 address."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("wan", {}).get("ipv6") or None
