"""Device tracker platform for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_ACTIVE,
    ATTR_CONNECTION_TYPE,
    ATTR_HOSTNAME,
    ATTR_INTERFACE,
    ATTR_IP,
    ATTR_LEASE_TIME,
    ATTR_MAC,
    ATTR_PHY_RATE,
    ATTR_RSSI,
    ATTR_SNR,
    CONF_ONLY_ACTIVE,
    DOMAIN,
)
from .coordinator import ZyxelDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device tracker entities for Zyxel EX3301-T0."""
    coordinator: ZyxelDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    tracked: set[str] = set()

    only_active = entry.options.get(CONF_ONLY_ACTIVE, False)

    @callback
    def async_add_devices(new_macs: list[str] | None = None) -> None:
        """Add newly discovered devices as entities."""
        entities: list[ZyxelDeviceTracker] = []
        macs_to_check = new_macs if new_macs is not None else list(coordinator.data.keys())

        for mac in macs_to_check:
            if mac in tracked:
                continue

            dev_data = coordinator.data.get(mac)
            if not dev_data:
                continue

            if only_active and not dev_data.get("active"):
                continue

            tracked.add(mac)
            entities.append(ZyxelDeviceTracker(coordinator, mac))

        if entities:
            async_add_entities(entities)

    # Add initial batch
    async_add_devices()

    # Listen for new devices discovered in future updates
    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_new_device, async_add_devices)
    )


class ZyxelDeviceTracker(CoordinatorEntity[ZyxelDataUpdateCoordinator], ScannerEntity):
    """Representation of a device tracked through Zyxel EX3301-T0."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZyxelDataUpdateCoordinator, mac: str) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{coordinator.entry_id}_{mac}"

    @property
    def _dev_data(self) -> dict[str, Any]:
        """Return the device data from the coordinator."""
        return self.coordinator.data.get(self._mac, {})

    @property
    def name(self) -> str | None:
        """Return the name of the entity."""
        hostname = self._dev_data.get("hostname")
        if hostname and hostname != "Unknown":
            return hostname
        return self._mac

    @property
    def is_connected(self) -> bool:
        """Return true if the device is connected to the router."""
        return bool(self._dev_data.get("is_connected", False))

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.ROUTER

    @property
    def ip_address(self) -> str | None:
        """Return the primary IPv4 address."""
        return self._dev_data.get("ip") or None

    @property
    def mac_address(self) -> str:
        """Return the MAC address of the device."""
        return self._mac

    @property
    def hostname(self) -> str | None:
        """Return the hostname of the device."""
        host = self._dev_data.get("hostname")
        return host if host and host != "Unknown" else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device state attributes."""
        data = self._dev_data
        attrs: dict[str, Any] = {
            ATTR_MAC: self._mac,
            ATTR_IP: data.get("ip"),
            ATTR_HOSTNAME: data.get("hostname"),
            ATTR_ACTIVE: data.get("active", False),
            ATTR_CONNECTION_TYPE: data.get("connection_type"),
            ATTR_INTERFACE: data.get("interface"),
            ATTR_LEASE_TIME: data.get("lease_time_remaining"),
        }
        if data.get("rssi") is not None and data.get("rssi") != 0:
            attrs[ATTR_RSSI] = data.get("rssi")
        if data.get("snr") is not None and data.get("snr") != 0:
            attrs[ATTR_SNR] = data.get("snr")
        if data.get("phy_rate") is not None and data.get("phy_rate") != 0:
            attrs[ATTR_PHY_RATE] = data.get("phy_rate")

        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this network client."""
        hostname = self._dev_data.get("hostname")
        friendly_name = hostname if (hostname and hostname != "Unknown") else self._mac
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self._mac)},
            default_name=friendly_name,
            identifiers={(DOMAIN, self._mac)},
            via_device=(DOMAIN, self.coordinator.entry_id),
        )
