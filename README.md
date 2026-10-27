# Zyxel EX3301-T0 (Digi) Device Tracker for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)](https://home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom Home Assistant integration that interacts with the **Zyxel EX3301-T0** router (commonly provided by **Digi** in Spain, Romania, and Italy, as well as standalone Zyxel OPAL firmware) to track connected devices (Ethernet and Wi-Fi) for local presence detection and network monitoring.

---

## ✨ Features

- **Local Presence Detection:** Tracks all devices (`home` / `not_home`) using the router's internal DHCP and ARP host tables (`/cgi-bin/DAL?oid=lanhosts`).
- **Cryptographic Handshake Support:** Fully handles the router's hybrid **RSA-2048 + AES-256-CBC** authentication handshake automatically.
- **Rich Device Attributes:**
  - MAC Address (normalized unique identifier)
  - Current IPv4 Address
  - Hostname
  - Connection type (`Ethernet` or `WiFi`)
  - Physical interface (e.g. `eth0.4`)
  - Remaining DHCP lease time
  - Wi-Fi signal metrics (`RSSI`, `SNR`, and `PhyRate` where applicable)
- **Router Overview Sensors:**
  - `sensor.<router>_active_devices`: Number of currently connected active devices.
  - `sensor.<router>_total_devices`: Total known registered devices.
- **Config Flow & Options Flow:**
  - Configurable directly from the Home Assistant UI (**Settings > Devices & Services**).
  - Configurable polling interval (default: 30s).
  - Configurable `consider_home` window (default: 180s) to prevent Wi-Fi power-saving flapping.
  - Option to track all known DHCP leases or only currently active devices.
- **100% Local & Private:** No cloud dependencies, no external servers.

---

## 📡 Supported Hardware & ISPs

- **Router Model:** Zyxel EX3301-T0
- **Compatible Models:** Zyxel DX3301-T0, WX3100-T0, and other Zyxel OPAL/ZCFG firmware variants.
- **Primary ISP:** **Digi** (Spain / Romania / Italy), as well as unbranded / generic Zyxel firmware.

---

## 📦 Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In Home Assistant, go to **HACS** > **Integrations**.
3. Click the three dots in the top-right corner and select **Custom repositories**.
4. Paste the URL of this repository:
   ```text
   https://github.com/<your-username>/ha-zyxel-ex3301
   ```
5. Set the category to **Integration** and click **Add**.
6. Find **Zyxel EX3301-T0 (Digi)** and click **Download**.
7. Restart Home Assistant.

### Method 2: Manual Installation

1. Copy the `custom_components/zyxel_ex3301` directory into your Home Assistant `<config>/custom_components/` folder.
2. Restart Home Assistant.

---

## ⚙️ Configuration

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration** in the bottom right.
3. Search for **Zyxel EX3301-T0 (Digi)**.
4. Fill in the connection form:
   - **Router IP / Host:** `192.168.1.1` (or your router's LAN IP)
   - **Username:** `user` (default)
   - **Password:** Your router admin/user password
   - **Update interval:** `30` seconds (configurable from 5s to 300s)
5. Click **Submit**.

---

## 🔧 Options & Tuning

Click **Configure** on the integration card at any time to adjust:
- **Scan interval:** How frequently Home Assistant polls the router.
- **Consider Home period:** Number of seconds to keep a device marked as `home` after it goes inactive, preventing rapid on/off flapping for smartphones entering deep sleep.
- **Only track currently active devices:** Toggle whether entities are created for all historical DHCP entries or only devices actively seen.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
