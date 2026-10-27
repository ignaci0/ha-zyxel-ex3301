"""Device tracker platform for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
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
    CONF_TRACK_NEW_DEVICES,
    CONF_TRACKED_DEVICES,
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

    tracked_devices_opt: list[str] | None = entry.options.get(CONF_TRACKED_DEVICES)
    track_new: bool = entry.options.get(CONF_TRACK_NEW_DEVICES, False)
    tracked_whitelist: set[str] | None = set(tracked_devices_opt) if tracked_devices_opt is not None else None

    # Clean up entity registry entries that were removed from whitelist in options
    ent_reg = er.async_get(hass)
    existing_entries = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    for entity_entry in existing_entries:
        if entity_entry.domain == "device_tracker":
            mac = entity_entry.unique_id.replace(f"{entry.entry_id}_", "")
            if tracked_whitelist is not None and mac not in tracked_whitelist:
                _LOGGER.info("Removing unwhitelisted device %s (%s)", entity_entry.entity_id, mac)
                ent_reg.async_remove(entity_entry.entity_id)

    @callback
    def async_add_devices(new_macs: list[str] | None = None) -> None:
        """Add newly discovered devices as entities if whitelisted."""
        entities: list[ZyxelDeviceTracker] = []
        macs_to_check = new_macs if new_macs is not None else list(coordinator.data.keys())

        for mac in macs_to_check:
            if mac in tracked:
                continue

            dev_data = coordinator.data.get(mac)
            if not dev_data:
                continue

            if tracked_whitelist is not None:
                if mac not in tracked_whitelist:
                    if not track_new:
                        continue
                    tracked_whitelist.add(mac)

            tracked.add(mac)
            entities.append(ZyxelDeviceTracker(coordinator, mac))

        if entities:
            async_add_entities(entities)

    # Initial batch setup
    async_add_devices()

    # Listen for newly seen devices
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
        """Return the friendly name of the entity."""
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
