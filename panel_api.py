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
    Sub-path install support: PANEL_URL includes base path.
    Auth: GET / -> cookie -> POST /login JSON
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in: bool = False

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            jar = aiohttp.CookieJar(unsafe=True)
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                connector=connector,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
                    "Accept": "application/json, text/plain, */*",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        return self._session

    async def login(self) -> bool:
        """
        Auth flow:
          1. GET /  -> receive session cookie
          2. POST /login with JSON body {username, password}
        """
        session = await self._get_session()
        self._logged_in = False

        # Step 1: fetch root to plant the session cookie
        try:
            async with session.get(
                self._url("/"),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                logger.info(f"[auth] GET / -> {resp.status}")
                await resp.read()
        except Exception as e:
            logger.error(f"[auth] GET / failed: {e}")
            return False

        # Step 2: try JSON login first (newer 3x-ui versions)
        ok = await self._login_json(session)
        if ok:
            return True

        # Step 3: fallback to form-urlencoded
        ok = await self._login_form(session)
        return ok

    async def _login_json(self, session: aiohttp.ClientSession) -> bool:
        """POST /login with JSON body."""
        url = self._url("/login")
        body = {"username": self.username, "password": self.password}
        try:
            async with session.post(
                url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Referer": self._url("/"),
                    "Origin": self.base_url,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"[auth] POST /login JSON -> {resp.status}")
                raw = await resp.text()
                logger.info(f"[auth] body: {raw[:300]}")
                if resp.status == 403:
                    return False
                result = json.loads(raw)
                if result.get("success"):
                    logger.info("[auth] JSON login OK")
                    self._logged_in = True
                    return True
                logger.warning(f"[auth] JSON login fail: {result}")
                return False
        except Exception as e:
            logger.warning(f"[auth] JSON login exception: {e}")
            return False

    async def _login_form(self, session: aiohttp.ClientSession) -> bool:
        """POST /login with application/x-www-form-urlencoded."""
        url = self._url("/login")
        payload = f"username={self.username}&password={self.password}"
        try:
            async with session.post(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": self._url("/"),
                    "Origin": self.base_url,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                logger.info(f"[auth] POST /login FORM -> {resp.status}")
                raw = await resp.text()
                logger.info(f"[auth] body: {raw[:300]}")
                if resp.status == 403:
                    logger.error("[auth] 403 on form login too")
                    return False
                result = json.loads(raw)
                if result.get("success"):
                    logger.info("[auth] FORM login OK")
                    self._logged_in = True
                    return True
                logger.error(f"[auth] FORM login fail: {result}")
                return False
        except Exception as e:
            logger.error(f"[auth] FORM login exception: {e}")
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
                logger.info(f"[api] {method} {path} -> {resp.status}")
                if resp.status in (401, 403) and retry_login:
                    logger.warning("[api] re-logging in...")
                    ok = await self.login()
                    if ok:
                        return await self._request(method, path, data, json_data, retry_login=False)
                    return None
                raw = await resp.text()
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    logger.error(f"[api] non-JSON {method} {path}: {raw[:200]}")
                    return None
        except Exception as e:
            logger.error(f"[api] error {method} {url}: {e}")
            return None

    async def get_inbounds(self) -> Optional[List[Dict]]:
        if not self._logged_in:
            ok = await self.login()
            if not ok:
                return None
        result = await self._request("GET", "/xui/API/inbounds", retry_login=True)
        if result and result.get("success"):
            return result.get("obj", [])
        logger.error(f"get_inbounds failed: {result}")
        return None

    async def get_inbound(self, inbound_id: int) -> Optional[Dict]:
        if not self._logged_in:
            await self.login()
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
        if not self._logged_in:
            await self.login()
        inbound = await self.get_inbound(inbound_id)
        if not inbound:
            return None
        protocol = inbound.get("protocol", "").lower()
        expiry_ms = 0
        if expiry_days > 0:
            expiry_ms = int((datetime.now() + timedelta(days=expiry_days)).timestamp() * 1000)
        total_bytes = int(traffic_gb * 1024 ** 3) if traffic_gb > 0 else 0
        builders = {
            "vmess": self._build_vmess_client,
            "vless": self._build_vless_client,
            "trojan": self._build_trojan_client,
            "shadowsocks": self._build_shadowsocks_client,
        }
        builder = builders.get(protocol)
        if not builder:
            return {"success": False, "msg": f"Протокол '{protocol}' не поддерживается"}
        client = builder(email, tg_id, limit_ip, expiry_ms, total_bytes)
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client]})}
        return await self._request("POST", "/xui/API/inbounds/addClient", json_data=payload)

    async def get_client_link(self, inbound_id, email):
        result = await self._request("GET", f"/xui/API/inbounds/getClientUrl/{inbound_id}/{email}")
        return result.get("obj", "") if result and result.get("success") else None

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
