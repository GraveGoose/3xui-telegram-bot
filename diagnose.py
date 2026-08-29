#!/usr/bin/env python3
"""
Diagnostic script for 3x-ui panel connectivity.
Run: python diagnose.py
"""
import asyncio
import aiohttp
import json
import os
from dotenv import load_dotenv

load_dotenv()

PANEL_URL = os.getenv("PANEL_URL", "").rstrip("/")
PANEL_USERNAME = os.getenv("PANEL_USERNAME", "")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "")


async def diagnose():
    print(f"\n{'='*60}")
    print(f"Panel URL : {PANEL_URL}")
    print(f"Username  : {PANEL_USERNAME}")
    print(f"{'='*60}\n")

    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": PANEL_URL + "/",
        "Origin": PANEL_URL,
    }

    async with aiohttp.ClientSession(cookie_jar=jar, connector=connector, headers=headers) as session:

        # Step 1: GET root -> get session cookie
        print("[1] GET / (obtain session cookie)...")
        try:
            async with session.get(PANEL_URL + "/", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"    Status : {resp.status}")
                cookies = {k: v.value[:40]+"..." for k, v in session.cookie_jar.filter_cookies(PANEL_URL).items()}
                print(f"    Cookies: {cookies}")
                await resp.read()
        except Exception as e:
            print(f"    ERROR: {e}")
            return

        # Step 2: POST /login WITH the session cookie
        print("\n[2] POST /login (with session cookie)...")
        payload = f"username={PANEL_USERNAME}&password={PANEL_PASSWORD}"
        try:
            async with session.post(
                PANEL_URL + "/login",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                print(f"    Status : {resp.status}")
                print(f"    Content-Type: {resp.headers.get('Content-Type', '-')}")
                body = await resp.text()
                print(f"    Body   : {body[:400]}")
                cookies = {k: v.value[:40]+"..." for k, v in session.cookie_jar.filter_cookies(PANEL_URL).items()}
                print(f"    Cookies: {cookies}")
        except Exception as e:
            print(f"    ERROR: {e}")
            return

        # Step 3: GET /xui/API/inbounds
        print("\n[3] GET /xui/API/inbounds...")
        try:
            async with session.get(PANEL_URL + "/xui/API/inbounds", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"    Status : {resp.status}")
                body = await resp.text()
                try:
                    parsed = json.loads(body)
                    print(f"    Success: {parsed.get('success')}")
                    objs = parsed.get('obj', [])
                    print(f"    Inbounds: {len(objs)}")
                    for ib in objs:
                        print(f"      ID={ib.get('id')} {ib.get('remark','?')} [{ib.get('protocol','?')}] :{ib.get('port','?')}")
                except Exception:
                    print(f"    Body: {body[:300]}")
        except Exception as e:
            print(f"    ERROR: {e}")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    asyncio.run(diagnose())
