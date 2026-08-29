import aiohttp
import json
import uuid
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class XUIPanel:
    """
    Async HTTP client for 3x-ui panel API.
    Docs: https://github.com/MHSanaei/3x-ui (API section)
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._cookies: Optional[aiohttp.CookieJar] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar()
            self._session = aiohttp.ClientSession(cookie_jar=jar)
        return self._session

    async def login(self) -> bool:
        """Login to panel. Returns True on success."""
        session = await self._get_session()
        url = f"{self.base_url}/login"
        data = {"username": self.username, "password": self.password}
        try:
            async with session.post(url, data=data, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                result = await resp.json()
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
        endpoint: str,
        data: Any = None,
        json_data: Any = None,
        retry_login: bool = True
    ) -> Optional[Dict]:
        """Generic authenticated request with auto re-login."""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        try:
            async with session.request(
                method, url,
                data=data,
                json=json_data,
                ssl=False,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 401 and retry_login:
                    logger.info("Session expired, re-logging in...")
                    ok = await self.login()
                    if ok:
                        return await self._request(method, endpoint, data, json_data, retry_login=False)
                    return None
                try:
                    return await resp.json()
                except Exception:
                    text = await resp.text()
                    logger.error(f"Non-JSON response: {text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"Request error [{method} {url}]: {e}")
            return None

    async def get_inbounds(self) -> Optional[List[Dict]]:
        """Get all inbounds from panel."""
        await self.login()
        result = await self._request("GET", "/xui/API/inbounds")
        if result and result.get("success"):
            return result.get("obj", [])
        logger.error(f"Failed to get inbounds: {result}")
        return None

    async def get_inbound(self, inbound_id: int) -> Optional[Dict]:
        """Get single inbound by ID."""
        result = await self._request("GET", f"/xui/API/inbounds/get/{inbound_id}")
        if result and result.get("success"):
            return result.get("obj")
        return None

    def _build_vmess_client(self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int) -> Dict:
        return {
            "id": str(uuid.uuid4()),
            "alterId": 0,
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": str(uuid.uuid4()).replace("-", "")[:16],
            "comment": f"tg:{tg_id}"
        }

    def _build_vless_client(self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int) -> Dict:
        return {
            "id": str(uuid.uuid4()),
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": str(uuid.uuid4()).replace("-", "")[:16],
            "comment": f"tg:{tg_id}"
        }

    def _build_trojan_client(self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int) -> Dict:
        return {
            "password": str(uuid.uuid4()),
            "flow": "",
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": str(uuid.uuid4()).replace("-", "")[:16],
            "comment": f"tg:{tg_id}"
        }

    def _build_shadowsocks_client(self, email: str, tg_id: str, limit_ip: int, expiry_ms: int, total_bytes: int) -> Dict:
        return {
            "password": str(uuid.uuid4()),
            "email": email,
            "limitIp": limit_ip,
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": tg_id,
            "subId": str(uuid.uuid4()).replace("-", "")[:16],
            "comment": f"tg:{tg_id}"
        }

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        tg_id: str,
        limit_ip: int = 0,
        expiry_days: int = 0,
        traffic_gb: float = 0
    ) -> Optional[Dict]:
        """
        Add a client to an inbound.
        Supports vmess, vless, trojan, shadowsocks.
        """
        inbound = await self.get_inbound(inbound_id)
        if not inbound:
            logger.error(f"Inbound {inbound_id} not found")
            return None

        protocol = inbound.get("protocol", "").lower()
        expiry_ms = 0
        if expiry_days > 0:
            expiry_dt = datetime.now() + timedelta(days=expiry_days)
            expiry_ms = int(expiry_dt.timestamp() * 1000)

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
            return {"success": False, "msg": f"Протокол {protocol} не поддерживается"}

        client = builder(email, tg_id, limit_ip, expiry_ms, total_bytes)

        payload = {
            "id": inbound_id,
            "settings": json.dumps({"clients": [client]})
        }

        result = await self._request("POST", f"/xui/API/inbounds/addClient", json_data=payload)
        logger.info(f"addClient result: {result}")
        return result

    async def get_client_link(self, inbound_id: int, email: str) -> Optional[str]:
        """
        Get connection link (URI) for a client.
        Uses /xui/API/inbounds/getClientUrl/{inbound_id}/{email}
        """
        result = await self._request("GET", f"/xui/API/inbounds/getClientUrl/{inbound_id}/{email}")
        if result and result.get("success"):
            return result.get("obj", "")
        # Fallback: try get_inbound and build URI manually
        return None

    async def get_client_stats(self, email: str) -> Optional[Dict]:
        """Get client traffic stats by email."""
        result = await self._request("GET", f"/xui/API/inbounds/getClientTraffics/{email}")
        if result and result.get("success"):
            return result.get("obj")
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        """Delete a client by UUID."""
        result = await self._request("POST", f"/xui/API/inbounds/{inbound_id}/delClient/{client_uuid}")
        return result and result.get("success", False)

    async def reset_client_traffic(self, inbound_id: int, email: str) -> bool:
        """Reset traffic for a client."""
        result = await self._request("POST", f"/xui/API/inbounds/{inbound_id}/resetClientTraffic/{email}")
        return result and result.get("success", False)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
