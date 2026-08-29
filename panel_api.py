import aiohttp
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class XUIPanel:
    """
    Async HTTP client for 3x-ui panel API.
    Supports panels with custom base paths, e.g.:
      http://1.2.3.4:54321            -> standard install
      https://host:port/secretpath    -> sub-path install

    PANEL_URL must include the full base path without trailing slash.
    Example: https://45.43.77.169:1488/8spqLzfgXxcUlggSB8
    """

    def __init__(self, base_url: str, username: str, password: str):
        # Strip trailing slash, keep everything else including sub-path
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None

    def _url(self, path: str) -> str:
        """Build full URL: base_url + /path (path must start with /)"""
        return f"{self.base_url}{path}"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return existing session or create a new one with a shared cookie jar."""
        if self._session is None or self._session.closed:
            # unsafe=True needed for IP-based URLs (no hostname validation)
            jar = aiohttp.CookieJar(unsafe=True)
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                connector=connector,
            )
        return self._session

    async def login(self) -> bool:
        """POST to /login. Stores session cookie automatically."""
        session = await self._get_session()
        url = self._url("/login")
        # 3x-ui expects form data, not JSON
        form = aiohttp.FormData()
        form.add_field("username", self.username)
        form.add_field("password", self.password)
        try:
            async with session.post(
                url,
                data=form,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"Login HTTP status: {resp.status}")
                ct = resp.headers.get("Content-Type", "")
                logger.info(f"Login Content-Type: {ct}")
                raw = await resp.text()
                logger.debug(f"Login raw response: {raw[:300]}")
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    logger.error(f"Login: non-JSON response: {raw[:200]}")
                    return False
                if result.get("success"):
                    logger.info("Panel login successful")
                    return True
                logger.error(f"Panel login failed: {result}")
                return False
        except Exception as e:
            logger.error(f"Panel login error: {e}")
            return False

    async def _request(
        self,
        method: str,
        path: str,
        data: Any = None,
        json_data: Any = None,
        retry_login: bool = True,
    ) -> Optional[Dict]:
        """Authenticated request. Auto re-login on 401."""
        session = await self._get_session()
        url = self._url(path)
        try:
            async with session.request(
                method,
                url,
                data=data,
                json=json_data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"[{method}] {url} -> HTTP {resp.status}")
                if resp.status in (401, 403) and retry_login:
                    logger.info("Session expired or forbidden, re-logging in...")
                    ok = await self.login()
                    if ok:
                        return await self._request(method, path, data, json_data, retry_login=False)
                    return None
                raw = await resp.text()
                logger.debug(f"Response: {raw[:300]}")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    logger.error(f"Non-JSON response [{method} {url}]: {raw[:200]}")
                    return None
        except Exception as e:
            logger.error(f"Request error [{method} {url}]: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Inbounds
    # ------------------------------------------------------------------ #

    async def get_inbounds(self) -> Optional[List[Dict]]:
        """Get all inbounds."""
        logged_in = await self.login()
        if not logged_in:
            return None
        result = await self._request("GET", "/xui/API/inbounds", retry_login=False)
        if result and result.get("success"):
            return result.get("obj", [])
        logger.error(f"Failed to get inbounds: {result}")
        return None

    async def get_inbound(self, inbound_id: int) -> Optional[Dict]:
        """Get a single inbound by ID."""
        result = await self._request("GET", f"/xui/API/inbounds/get/{inbound_id}")
        if result and result.get("success"):
            return result.get("obj")
        return None

    # ------------------------------------------------------------------ #
    #  Client builders per protocol
    # ------------------------------------------------------------------ #

    @staticmethod
    def _sub_id() -> str:
        return uuid.uuid4().hex[:16]

    def _build_vmess_client(
        self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int
    ) -> Dict:
        return {
            "id": str(uuid.uuid4()),
            "alterId": 0,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": self._sub_id(),
            "comment": f"tg:{tg_id}",
        }

    def _build_vless_client(
        self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int
    ) -> Dict:
        return {
            "id": str(uuid.uuid4()),
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": self._sub_id(),
            "comment": f"tg:{tg_id}",
        }

    def _build_trojan_client(
        self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int
    ) -> Dict:
        return {
            "password": str(uuid.uuid4()),
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": self._sub_id(),
            "comment": f"tg:{tg_id}",
        }

    def _build_shadowsocks_client(
        self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int
    ) -> Dict:
        return {
            "password": str(uuid.uuid4()),
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": self._sub_id(),
            "comment": f"tg:{tg_id}",
        }

    # ------------------------------------------------------------------ #
    #  Add client
    # ------------------------------------------------------------------ #

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        tg_id: str,
        limit_ip: int = 0,
        expiry_days: int = 0,
        traffic_gb: float = 0,
    ) -> Optional[Dict]:
        """Add a client to an inbound. Supports vmess, vless, trojan, shadowsocks."""
        inbound = await self.get_inbound(inbound_id)
        if not inbound:
            logger.error(f"Inbound {inbound_id} not found")
            return None

        protocol = inbound.get("protocol", "").lower()

        expiry_ms = 0
        if expiry_days > 0:
            expiry_ms = int(
                (datetime.now() + timedelta(days=expiry_days)).timestamp() * 1000
            )
        total_bytes = int(traffic_gb * 1024 ** 3) if traffic_gb > 0 else 0

        builders = {
            "vmess": self._build_vmess_client,
            "vless": self._build_vless_client,
            "trojan": self._build_trojan_client,
            "shadowsocks": self._build_shadowsocks_client,
        }
        builder = builders.get(protocol)
        if not builder:
            logger.error(f"Unsupported protocol: {protocol}")
            return {"success": False, "msg": f"Протокол '{protocol}' не поддерживается"}

        client = builder(email, tg_id, limit_ip, expiry_ms, total_bytes)
        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client]}),
        }
        result = await self._request("POST", "/xui/API/inbounds/addClient", json_data=payload)
        logger.info(f"addClient result: {result}")
        return result

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    async def get_client_link(self, inbound_id: int, email: str) -> Optional[str]:
        """Get the connection URI for a client."""
        result = await self._request(
            "GET", f"/xui/API/inbounds/getClientUrl/{inbound_id}/{email}"
        )
        if result and result.get("success"):
            return result.get("obj", "")
        return None

    async def get_client_stats(self, email: str) -> Optional[Dict]:
        """Get traffic stats for a client by email."""
        result = await self._request(
            "GET", f"/xui/API/inbounds/getClientTraffics/{email}"
        )
        if result and result.get("success"):
            return result.get("obj")
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        """Delete a client by UUID."""
        result = await self._request(
            "POST", f"/xui/API/inbounds/{inbound_id}/delClient/{client_uuid}"
        )
        return bool(result and result.get("success"))

    async def reset_client_traffic(self, inbound_id: int, email: str) -> bool:
        """Reset traffic counter for a client."""
        result = await self._request(
            "POST", f"/xui/API/inbounds/{inbound_id}/resetClientTraffic/{email}"
        )
        return bool(result and result.get("success"))

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
