import aiohttp
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class XUIPanel:
    """
    Async HTTP client for 3x-ui panel API.
    PANEL_URL = full base URL including sub-path, no trailing slash.
    Example: https://45.43.77.169:1488/8spqLzfgXxcUlggSB8
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)  # unsafe=True for bare IP addresses
            connector = aiohttp.TCPConnector(ssl=False)  # skip TLS cert verification
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                connector=connector,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "User-Agent": "Mozilla/5.0",
                },
            )
        return self._session

    async def login(self) -> bool:
        """Login via POST /login with x-www-form-urlencoded body."""
        session = await self._get_session()
        url = self._url("/login")
        # Must be application/x-www-form-urlencoded (NOT multipart/form-data)
        payload = f"username={self.username}&password={self.password}"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            async with session.post(
                url,
                data=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"Login HTTP {resp.status}, Content-Type: {resp.headers.get('Content-Type', '-')}")
                raw = await resp.text()
                logger.info(f"Login response body: {raw[:300]}")
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    logger.error(f"Login: non-JSON response (status={resp.status}): '{raw[:200]}'")
                    return False
                if result.get("success"):
                    logger.info("Panel login successful")
                    return True
                logger.error(f"Panel login failed: {result}")
                return False
        except Exception as e:
            logger.error(f"Panel login exception: {e}")
            return False

    async def _request(
        self,
        method: str,
        path: str,
        data: Any = None,
        json_data: Any = None,
        retry_login: bool = True,
    ) -> Optional[Dict]:
        session = await self._get_session()
        url = self._url(path)
        try:
            async with session.request(
                method, url,
                data=data,
                json=json_data,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"[{method}] {path} -> HTTP {resp.status}")
                if resp.status in (401, 403) and retry_login:
                    logger.warning("Re-logging in after 401/403...")
                    ok = await self.login()
                    if ok:
                        return await self._request(method, path, data, json_data, retry_login=False)
                    return None
                raw = await resp.text()
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    logger.error(f"Non-JSON [{method} {path}]: {raw[:200]}")
                    return None
        except Exception as e:
            logger.error(f"Request error [{method} {url}]: {e}")
            return None

    async def get_inbounds(self) -> Optional[List[Dict]]:
        logged_in = await self.login()
        if not logged_in:
            return None
        result = await self._request("GET", "/xui/API/inbounds", retry_login=False)
        if result and result.get("success"):
            return result.get("obj", [])
        logger.error(f"get_inbounds failed: {result}")
        return None

    async def get_inbound(self, inbound_id: int) -> Optional[Dict]:
        result = await self._request("GET", f"/xui/API/inbounds/get/{inbound_id}")
        if result and result.get("success"):
            return result.get("obj")
        return None

    @staticmethod
    def _sub_id() -> str:
        return uuid.uuid4().hex[:16]

    def _build_vmess_client(self, email, tg_id, limit_ip, expiry_ms, total_bytes):
        return {"id": str(uuid.uuid4()), "alterId": 0, "email": email,
                "limitIp": limit_ip, "totalGB": total_bytes, "expiryTime": expiry_ms,
                "enable": True, "tgId": tg_id, "subId": self._sub_id(), "comment": f"tg:{tg_id}"}

    def _build_vless_client(self, email, tg_id, limit_ip, expiry_ms, total_bytes):
        return {"id": str(uuid.uuid4()), "flow": "", "email": email,
                "limitIp": limit_ip, "totalGB": total_bytes, "expiryTime": expiry_ms,
                "enable": True, "tgId": tg_id, "subId": self._sub_id(), "comment": f"tg:{tg_id}"}

    def _build_trojan_client(self, email, tg_id, limit_ip, expiry_ms, total_bytes):
        return {"password": str(uuid.uuid4()), "flow": "", "email": email,
                "limitIp": limit_ip, "totalGB": total_bytes, "expiryTime": expiry_ms,
                "enable": True, "tgId": tg_id, "subId": self._sub_id(), "comment": f"tg:{tg_id}"}

    def _build_shadowsocks_client(self, email, tg_id, limit_ip, expiry_ms, total_bytes):
        return {"password": str(uuid.uuid4()), "email": email,
                "limitIp": limit_ip, "totalGB": total_bytes, "expiryTime": expiry_ms,
                "enable": True, "tgId": tg_id, "subId": self._sub_id(), "comment": f"tg:{tg_id}"}

    async def add_client(self, inbound_id, email, tg_id, limit_ip=0, expiry_days=0, traffic_gb=0):
        inbound = await self.get_inbound(inbound_id)
        if not inbound:
            return None
        protocol = inbound.get("protocol", "").lower()
        expiry_ms = 0
        if expiry_days > 0:
            expiry_ms = int((datetime.now() + timedelta(days=expiry_days)).timestamp() * 1000)
        total_bytes = int(traffic_gb * 1024 ** 3) if traffic_gb > 0 else 0
        builders = {"vmess": self._build_vmess_client, "vless": self._build_vless_client,
                    "trojan": self._build_trojan_client, "shadowsocks": self._build_shadowsocks_client}
        builder = builders.get(protocol)
        if not builder:
            return {"success": False, "msg": f"Протокол '{protocol}' не поддерживается"}
        client = builder(email, tg_id, limit_ip, expiry_ms, total_bytes)
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client]})}
        return await self._request("POST", "/xui/API/inbounds/addClient", json_data=payload)

    async def get_client_link(self, inbound_id, email):
        result = await self._request("GET", f"/xui/API/inbounds/getClientUrl/{inbound_id}/{email}")
        if result and result.get("success"):
            return result.get("obj", "")
        return None

    async def get_client_stats(self, email):
        result = await self._request("GET", f"/xui/API/inbounds/getClientTraffics/{email}")
        return result.get("obj") if result and result.get("success") else None

    async def delete_client(self, inbound_id, client_uuid):
        r = await self._request("POST", f"/xui/API/inbounds/{inbound_id}/delClient/{client_uuid}")
        return bool(r and r.get("success"))

    async def reset_client_traffic(self, inbound_id, email):
        r = await self._request("POST", f"/xui/API/inbounds/{inbound_id}/resetClientTraffic/{email}")
        return bool(r and r.get("success"))

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
