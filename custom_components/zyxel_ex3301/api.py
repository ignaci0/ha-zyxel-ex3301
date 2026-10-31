"""Zyxel EX3301-T0 API client."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

_LOGGER = logging.getLogger(__name__)


class ZyxelError(Exception):
    """Base exception for Zyxel integration."""


class ZyxelAuthError(ZyxelError):
    """Exception raised when authentication fails."""


class ZyxelConnectionError(ZyxelError):
    """Exception raised on network/connectivity issues."""


def _encrypt_login_payload(username: str, password: str, rsa_pem: str) -> tuple[dict[str, str], bytes]:
    """Encrypt credentials using AES-256-CBC and RSA-2048."""
    pub_key = load_pem_public_key(rsa_pem.encode("utf-8"))

    aes_raw_key = os.urandom(32)
    aes_key_b64 = base64.b64encode(aes_raw_key).decode("ascii")

    aes_raw_iv = os.urandom(32)
    aes_iv_b64 = base64.b64encode(aes_raw_iv).decode("ascii")
    iv_16 = aes_raw_iv[:16]

    login_obj = {
        "Input_Account": username,
        "Input_Passwd": base64.b64encode(password.encode("utf-8")).decode("ascii"),
        "currLang": "es",
        "RememberPassword": 0,
        "SHA512_password": False,
    }
    plaintext = json.dumps(login_obj).encode("utf-8")

    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(aes_raw_key), modes.CBC(iv_16))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    encrypted_key = pub_key.encrypt(aes_key_b64.encode("ascii"), asym_padding.PKCS1v15())

    body = {
        "content": base64.b64encode(ciphertext).decode("ascii"),
        "key": base64.b64encode(encrypted_key).decode("ascii"),
        "iv": aes_iv_b64,
    }
    return body, aes_raw_key


def _encrypt_payload(payload: dict[str, Any], aes_raw_key: bytes) -> dict[str, str]:
    """Encrypt request body using AES-256-CBC."""
    aes_raw_iv = os.urandom(32)
    aes_iv_b64 = base64.b64encode(aes_raw_iv).decode("ascii")
    iv_16 = aes_raw_iv[:16]

    plaintext = json.dumps(payload).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(aes_raw_key), modes.CBC(iv_16))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    return {
        "content": base64.b64encode(ciphertext).decode("ascii"),
        "key": "",
        "iv": aes_iv_b64,
    }


def _decrypt_payload(content_b64: str, iv_b64: str, aes_raw_key: bytes) -> dict[str, Any]:
    """Decrypt payload using AES-256-CBC and unpad PKCS7."""
    iv_16 = base64.b64decode(iv_b64)[:16]
    ct = base64.b64decode(content_b64)

    cipher = Cipher(algorithms.AES(aes_raw_key), modes.CBC(iv_16))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    dec = unpadder.update(padded) + unpadder.finalize()
    return json.loads(dec.decode("utf-8"))


class ZyxelRouterApi:
    """API wrapper for Zyxel EX3301-T0 (Digi)."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Initialize the API client."""
        self.host = host.rstrip("/")
        if not self.host.startswith("http://") and not self.host.startswith("https://"):
            self.base_url = f"http://{self.host}"
        else:
            self.base_url = self.host
        self.username = username
        self.password = password
        self._external_session = session is not None
        self._session = session
        self._loop = loop or asyncio.get_event_loop()
        self._session_key: str | None = None
        self._aes_key: bytes | None = None
        self._model: str = "EX3301-T0"
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session with a cookie jar."""
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(cookie_jar=jar)
            self._external_session = False
        return self._session

    async def async_close(self) -> None:
        """Close the API session."""
        if not self._external_session and self._session and not self._session.closed:
            await self._session.close()

    async def async_login(self) -> bool:
        """Authenticate with the router using hybrid RSA/AES."""
        async with self._lock:
            return await self._login_locked()

    async def _login_locked(self) -> bool:
        """Internal login implementation holding lock."""
        session = await self._get_session()
        try:
            # 1. Fetch unauthenticated basic info
            async with session.get(
                f"{self.base_url}/GetInfoNoLogin",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise ZyxelConnectionError(f"Failed to fetch router info (HTTP {resp.status})")
                info = await resp.json(content_type=None)
                self._model = info.get("ModelName", "EX3301-T0")

            # 2. Fetch RSA public key
            async with session.get(
                f"{self.base_url}/getRSAPublickKey",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise ZyxelConnectionError(f"Failed to fetch RSA key (HTTP {resp.status})")
                rsa_data = await resp.json(content_type=None)
                rsa_pem = rsa_data.get("RSAPublicKey")

                if not rsa_pem:
                    raise ZyxelAuthError("Router did not return an RSA public key")

            # 3. Encrypt credentials in executor
            body, aes_key = await self._loop.run_in_executor(
                None, _encrypt_login_payload, self.username, self.password, rsa_pem
            )

            # 4. POST login payload
            async with session.post(
                f"{self.base_url}/UserLogin",
                json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    raise ZyxelAuthError(f"UserLogin HTTP error: {resp.status}")
                res_json = await resp.json(content_type=None)

            if "content" not in res_json or "iv" not in res_json:
                raise ZyxelAuthError("Invalid login response format from router")

            # 5. Decrypt login response in executor
            dec_login = await self._loop.run_in_executor(
                None, _decrypt_payload, res_json["content"], res_json["iv"], aes_key
            )

            if dec_login.get("result") != "ZCFG_SUCCESS":
                error_msg = dec_login.get("result", "Authentication failed")
                raise ZyxelAuthError(f"Login rejected: {error_msg}")

            session_key = dec_login.get("sessionkey")
            if not session_key:
                raise ZyxelAuthError("Router response did not contain a sessionkey")

            self._session_key = session_key
            self._aes_key = aes_key
            _LOGGER.debug("Successfully authenticated to %s (%s)", self.base_url, self._model)
            return True

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ZyxelConnectionError(f"Connection error to {self.base_url}: {err}") from err

    async def _fetch_dal_objects(self, oid: str, timeout: float = 10) -> list[dict[str, Any]]:
        """Fetch and decrypt DAL objects for a given OID with automatic re-auth.

        `timeout` is per call because the OIDs differ by an order of magnitude:
        status/wan answer in well under a second, while lanhosts rebuilds the
        whole host table on demand and takes ~10 s on an EX3301.
        """
        if not self._session_key:
            await self.async_login()

        for attempt in (1, 2):
            try:
                session = await self._get_session()
                headers = {
                    "CSRFToken": self._session_key or "",
                    "If-Modified-Since": "Thu, 01 Jun 1970 00:00:00 GMT",
                }
                async with session.get(
                    f"{self.base_url}/cgi-bin/DAL?oid={oid}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status in (401, 403):
                        raise ZyxelAuthError(f"Unauthorized (HTTP {resp.status})")
                    if resp.status != 200:
                        # Drain the body so the connection can go back to the pool.
                        await resp.read()
                        raise ZyxelConnectionError(f"HTTP error {resp.status} fetching oid={oid}")
                    data = await resp.json(content_type=None)

                if isinstance(data, dict) and "content" in data and "iv" in data:
                    if not self._aes_key:
                        raise ZyxelAuthError("No AES key stored for payload decryption")
                    data = await self._loop.run_in_executor(
                        None, _decrypt_payload, data["content"], data["iv"], self._aes_key
                    )

                if isinstance(data, dict):
                    if data.get("result") not in ("ZCFG_SUCCESS", None):
                        raise ZyxelAuthError(f"Router returned error: {data.get('result')}")
                    objects = data.get("Object", [])
                    if isinstance(objects, list):
                        return objects

                return []
            except ZyxelAuthError:
                if attempt == 1:
                    _LOGGER.info("Session expired for %s, re-authenticating...", self.base_url)
                    await self.async_login()
                else:
                    raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                error = ZyxelConnectionError(f"Communication error: {err}")
                if attempt == 1:
                    _LOGGER.debug("DAL oid=%s failed (attempt 1): %s - retrying", oid, error)
                    await asyncio.sleep(3)
                else:
                    raise error from err

        return []

    async def async_get_lanhosts(self) -> list[dict[str, Any]]:
        """Fetch and decrypt the list of LAN and WLAN hosts."""
        objects = await self._fetch_dal_objects("lanhosts", timeout=30)
        if objects and isinstance(objects, list):
            return objects[0].get("lanhosts", [])
        return []

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch router status (SystemInfo, DeviceInfo, LanPortInfo)."""
        objects = await self._fetch_dal_objects("status")
        if objects and isinstance(objects, list):
            return objects[0]
        return {}

    async def async_get_wan(self) -> list[dict[str, Any]]:
        """Fetch WAN interfaces."""
        return await self._fetch_dal_objects("wan")

    async def async_get_led_status(self) -> bool:
        """Fetch LED status (True if LEDs are on, False if stealth/off)."""
        if not self._session_key:
            await self.async_login()

        for attempt in (1, 2):
            try:
                session = await self._get_session()
                headers = {
                    "CSRFToken": self._session_key or "",
                    "If-Modified-Since": "Thu, 01 Jun 1970 00:00:00 GMT",
                }
                async with session.get(
                    f"{self.base_url}/cgi-bin/LEDStatus",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (401, 403):
                        raise ZyxelAuthError(f"Unauthorized (HTTP {resp.status})")
                    if resp.status != 200:
                        raise ZyxelConnectionError(f"HTTP error {resp.status} fetching LEDStatus")
                    data = await resp.json(content_type=None)

                if isinstance(data, dict) and "content" in data and "iv" in data:
                    if not self._aes_key:
                        raise ZyxelAuthError("No AES key stored for payload decryption")
                    data = await self._loop.run_in_executor(
                        None, _decrypt_payload, data["content"], data["iv"], self._aes_key
                    )

                return bool(data.get("isactive", False))
            except ZyxelAuthError:
                if attempt == 1:
                    _LOGGER.info("Session expired for %s, re-authenticating...", self.base_url)
                    await self.async_login()
                else:
                    raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise ZyxelConnectionError(f"Communication error: {err}") from err

        return False

    async def async_set_led_status(self, status: bool) -> bool:
        """Set LED status (True = on, False = off)."""
        if not self._session_key or not self._aes_key:
            await self.async_login()

        for attempt in (1, 2):
            try:
                session = await self._get_session()
                headers = {
                    "CSRFToken": self._session_key or "",
                    "If-Modified-Since": "Thu, 01 Jun 1970 00:00:00 GMT",
                }
                body = await self._loop.run_in_executor(
                    None, _encrypt_payload, {"status": status}, self._aes_key
                )
                async with session.put(
                    f"{self.base_url}/cgi-bin/LEDStatus",
                    json=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (401, 403):
                        raise ZyxelAuthError(f"Unauthorized (HTTP {resp.status})")
                    if resp.status != 200:
                        raise ZyxelConnectionError(f"HTTP error {resp.status} setting LEDStatus")
                    data = await resp.json(content_type=None)

                if isinstance(data, dict) and "content" in data and "iv" in data:
                    data = await self._loop.run_in_executor(
                        None, _decrypt_payload, data["content"], data["iv"], self._aes_key
                    )

                return bool(data.get("isactive", status))
            except ZyxelAuthError:
                if attempt == 1:
                    _LOGGER.info("Session expired for %s, re-authenticating...", self.base_url)
                    await self.async_login()
                else:
                    raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise ZyxelConnectionError(f"Communication error: {err}") from err

        return status

    async def async_reboot(self) -> bool:
        """Trigger router reboot."""
        if not self._session_key:
            await self.async_login()

        session = await self._get_session()
        headers = {
            "CSRFToken": self._session_key or "",
            "If-Modified-Since": "Thu, 01 Jun 1970 00:00:00 GMT",
        }
        try:
            async with session.post(
                f"{self.base_url}/cgi-bin/Reboot",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                _LOGGER.info("Router reboot initiated (HTTP %s)", resp.status)
                return resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.info("Router reboot triggered (connection reset: %s)", err)
            return True

    async def async_logout(self) -> None:
        """Log out from the router."""
        if not self._session_key:
            return

        session = await self._get_session()
        headers = {"CSRFToken": self._session_key}
        try:
            async with session.post(
                f"{self.base_url}/cgi-bin/UserLogout",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                await resp.read()
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Logout request ignored error: %s", err)
        finally:
            self._session_key = None
            self._aes_key = None

    @property
    def model(self) -> str:
        """Return discovered router model."""
        return self._model
