"""Binary sensor platform for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
    """Set up binary sensors for Zyxel EX3301-T0."""
    coordinator: ZyxelDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    entities: list[BinarySensorEntity] = [
        ZyxelWanStatusBinarySensor(coordinator, entry),
    ]

    # Add binary sensors for each LAN/WAN port reported by the router
    ports = coordinator.data.get("ports", {}) if coordinator.data else {}
    for port_name in ports:
        entities.append(ZyxelLanPortBinarySensor(coordinator, entry, port_name))

    async_add_entities(entities)


class ZyxelBaseBinarySensor(CoordinatorEntity[ZyxelDataUpdateCoordinator], BinarySensorEntity):
    """Base binary sensor for Zyxel router."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize base binary sensor."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info linking this entity to the router device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
        )


class ZyxelWanStatusBinarySensor(ZyxelBaseBinarySensor):
    """Binary sensor indicating WAN Internet connection state."""

    _attr_translation_key = "wan_status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize WAN status binary sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_wan_status"

    @property
    def is_on(self) -> bool:
        """Return true if WAN is connected."""
        if not self.coordinator.data:
            return False
        return bool(self.coordinator.data.get("wan", {}).get("connected", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return WAN attributes."""
        if not self.coordinator.data:
            return {}
        wan = self.coordinator.data.get("wan", {})
        return {
            "ip_address": wan.get("ip"),
            "ipv6_address": wan.get("ipv6"),
            "gateway": wan.get("gateway"),
            "dns": wan.get("dns"),
        }


class ZyxelLanPortBinarySensor(ZyxelBaseBinarySensor):
    """Binary sensor indicating link state for a specific physical port."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: ZyxelDataUpdateCoordinator, entry: ConfigEntry, port_name: str
    ) -> None:
        """Initialize LAN port binary sensor."""
        super().__init__(coordinator, entry)
        self._port_name = port_name
        self._attr_name = f"Port {port_name}"
        self._attr_unique_id = f"{entry.entry_id}_port_{port_name.lower()}"

    @property
    def _port_data(self) -> dict[str, Any]:
        """Return data for this port."""
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("ports", {}).get(self._port_name, {})

    @property
    def is_on(self) -> bool:
        """Return true if port link is up."""
        return bool(self._port_data.get("up", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return port link speed and duplex attributes."""
        data = self._port_data
        speed = data.get("speed", 0)
        return {
            "link_speed": f"{speed} Mbps" if data.get("up") else "Disconnected",
            "bitrate_mbps": speed,
            "duplex": data.get("duplex"),
            "interface": data.get("interface"),
            "mac_address": data.get("mac"),
        }
