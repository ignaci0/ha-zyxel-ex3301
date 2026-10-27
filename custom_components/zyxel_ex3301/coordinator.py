"""DataUpdateCoordinator for Zyxel EX3301-T0 (Digi)."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ZyxelAuthError, ZyxelConnectionError, ZyxelRouterApi
from .const import CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ZyxelDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
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

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch client data from the router."""
        try:
            raw_hosts = await self.api.async_get_lanhosts()
        except ZyxelAuthError as err:
            raise UpdateFailed(f"Authentication failed on {self.api.base_url}: {err}") from err
        except ZyxelConnectionError as err:
            raise UpdateFailed(f"Communication error with {self.api.base_url}: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

        now = dt_util.utcnow()
        consider_home = self.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
        consider_delta = timedelta(seconds=consider_home)

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

        return devices
