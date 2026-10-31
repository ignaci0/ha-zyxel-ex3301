"""DataUpdateCoordinator for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ZyxelAuthError, ZyxelConnectionError, ZyxelRouterApi
from .const import CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ZyxelDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Zyxel router data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ZyxelRouterApi,
        scan_interval: int,
        entry_id: str,
        router_device_id: str,
        options: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.entry_id = entry_id
        self.router_device_id = router_device_id
        self.options = options
        self._known_macs: set[str] = set()
        self._last_active_timestamps: dict[str, datetime] = {}

    @property
    def signal_new_device(self) -> str:
        """Signal name for notifying newly discovered devices."""
        return f"{DOMAIN}_{self.entry_id}_new_device"

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch all data from the router."""
        try:
            raw_hosts, status_obj, wan_objs, led_status = await asyncio.gather(
                self.api.async_get_lanhosts(),
                self.api.async_get_status(),
                self.api.async_get_wan(),
                self.api.async_get_led_status(),
                return_exceptions=True,
            )
        except Exception as err:
            raise UpdateFailed(f"Unexpected coordinator gather error: {err}") from err

        if isinstance(raw_hosts, Exception):
            if isinstance(raw_hosts, ZyxelAuthError):
                raise UpdateFailed(f"Authentication failed on {self.api.base_url}: {raw_hosts}") from raw_hosts
            if isinstance(raw_hosts, ZyxelConnectionError):
                raise UpdateFailed(f"Communication error with {self.api.base_url}: {raw_hosts}") from raw_hosts
            raise UpdateFailed(f"Failed to fetch lanhosts: {raw_hosts}") from raw_hosts

        if isinstance(status_obj, Exception):
            _LOGGER.warning("Error fetching router status: %s", status_obj)
            status_obj = {}

        if isinstance(wan_objs, Exception):
            _LOGGER.warning("Error fetching router WAN info: %s", wan_objs)
            wan_objs = []

        if isinstance(led_status, Exception):
            _LOGGER.warning("Error fetching router LED status: %s", led_status)
            led_status = False

        now = dt_util.utcnow()
        consider_home = self.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
        consider_delta = timedelta(seconds=consider_home)

        # 1. Process connected devices
        devices: dict[str, dict[str, Any]] = {}
        new_macs: list[str] = []

        for host in raw_hosts:
            raw_mac = host.get("PhysAddress")
            if not raw_mac:
                continue

            mac = raw_mac.lower().strip()
            is_active = bool(host.get("Active", False))

            if is_active:
                self._last_active_timestamps[mac] = now
                state_connected = True
            else:
                last_active = self._last_active_timestamps.get(mac)
                if last_active and (now - last_active) <= consider_delta:
                    state_connected = True
                else:
                    state_connected = False

            device_info = {
                "mac": mac,
                "ip": host.get("IPAddress", ""),
                "hostname": host.get("HostName") or "Unknown",
                "active": is_active,
                "is_connected": state_connected,
                "connection_type": host.get("X_ZYXEL_ConnectionType") or host.get("InterfaceType", "Unknown"),
                "interface": host.get("Layer1Interface", ""),
                "lease_time_remaining": host.get("LeaseTimeRemaining", 0),
                "rssi": host.get("X_ZYXEL_RSSI", 0),
                "snr": host.get("X_ZYXEL_SNR", 0),
                "phy_rate": host.get("X_ZYXEL_PhyRate", 0),
                "last_seen": now if is_active else self._last_active_timestamps.get(mac, now),
            }

            devices[mac] = device_info

            if mac not in self._known_macs:
                self._known_macs.add(mac)
                new_macs.append(mac)

        if new_macs:
            _LOGGER.debug("Discovered %d new device(s) on %s: %s", len(new_macs), self.api.base_url, new_macs)
            async_dispatcher_send(self.hass, self.signal_new_device, new_macs)

        # 2. Process system & device info
        sys_info = status_obj.get("SystemInfo", {})
        dev_info = status_obj.get("DeviceInfo", {})

        total_mem = sys_info.get("Total", 0)
        free_mem = sys_info.get("Free", 0)
        mem_usage = round(((total_mem - free_mem) / total_mem) * 100, 1) if total_mem > 0 else 0.0

        sw_version = dev_info.get("SoftwareVersion")
        serial_number = dev_info.get("SerialNumber")

        # Update Home Assistant device registry with firmware and serial number if available
        if self.router_device_id and sw_version:
            dev_reg = dr.async_get(self.hass)
            dev_reg.async_update_device(
                self.router_device_id,
                sw_version=sw_version,
                serial_number=serial_number,
            )

        system = {
            "cpu_usage": sys_info.get("CPUUsage", 0),
            "memory_usage": mem_usage,
            "total_memory_kb": total_mem,
            "free_memory_kb": free_mem,
            "uptime": dev_info.get("UpTime", 0),
            "software_version": sw_version,
            "serial_number": serial_number,
            "hostname": sys_info.get("HostName", "EX3301-T0"),
        }

        # 3. Process WAN interfaces
        wan_entry = next((w for w in wan_objs if w.get("Name") == "ETHWAN"), None)
        if not wan_entry and wan_objs:
            wan_entry = wan_objs[0]

        wan_ip = wan_entry.get("IPAddress", "") if wan_entry else ""
        wan_connected = bool(wan_entry.get("Enable")) and bool(wan_ip) if wan_entry else False

        wan = {
            "connected": wan_connected,
            "ip": wan_ip,
            "ipv6": wan_entry.get("IP6Address", "") if wan_entry else "",
            "gateway": wan_entry.get("GatewayIPAddress", "") if wan_entry else "",
            "dns": wan_entry.get("DNSServer", "") if wan_entry else "",
            "name": wan_entry.get("Name", "ETHWAN") if wan_entry else "ETHWAN",
        }

        # 4. Process LAN/WAN port status
        lan_ports_raw = status_obj.get("LanPortInfo", [])
        ports: dict[str, dict[str, Any]] = {}
        for p in lan_ports_raw:
            port_name = p.get("X_ZYXEL_LanPort") or p.get("Name")
            if not port_name:
                continue
            status_str = p.get("Status", "Down")
            is_up = status_str.lower() == "up"
            ports[port_name] = {
                "name": port_name,
                "up": is_up,
                "status": status_str,
                "speed": p.get("CurrentBitRate", 0),
                "duplex": p.get("DuplexMode", "Auto"),
                "interface": p.get("Name", ""),
                "mac": p.get("MACAddress", ""),
            }

        return {
            "devices": devices,
            "system": system,
            "wan": wan,
            "ports": ports,
            "led_status": bool(led_status),
        }
