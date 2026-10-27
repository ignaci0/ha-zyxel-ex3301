"""Constants for the Zyxel EX3301-T0 (Digi) integration."""

DOMAIN = "zyxel_ex3301"

DEFAULT_NAME = "Zyxel EX3301-T0"
DEFAULT_HOST = "192.168.1.1"
DEFAULT_USERNAME = "user"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_CONSIDER_HOME = 180

CONF_CONSIDER_HOME = "consider_home"
CONF_TRACK_NEW_DEVICES = "track_new_devices"
CONF_ONLY_ACTIVE = "only_active"

ATTR_CONNECTION_TYPE = "connection_type"
ATTR_INTERFACE = "interface"
ATTR_LEASE_TIME = "lease_time_remaining"
ATTR_RSSI = "rssi"
ATTR_SNR = "snr"
ATTR_PHY_RATE = "phy_rate"
ATTR_ACTIVE = "active"
ATTR_MAC = "mac_address"
ATTR_IP = "ip_address"
ATTR_HOSTNAME = "hostname"
