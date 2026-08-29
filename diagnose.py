#!/usr/bin/env python3
"""
Diagnostic script for 3x-ui panel connectivity.
Run: python diagnose.py
Shows exactly what the panel returns at each step.
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
    print(f"Password  : {'*' * len(PANEL_PASSWORD)}")
    print(f"{'='*60}\n")

    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(
        cookie_jar=jar,
        connector=connector,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
    ) as session:

        # ---- Step 1: GET the panel root ----
        print("[1] GET panel root...")
        try:
            async with session.get(PANEL_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"    Status : {resp.status}")
                print(f"    Headers: {dict(resp.headers)}")
                body = await resp.text()
                print(f"    Body   : {body[:200]}\n")
        except Exception as e:
            print(f"    ERROR: {e}\n")

        # ---- Step 2: POST /login with form-urlencoded ----
        print("[2] POST /login (application/x-www-form-urlencoded)...")
        login_url = f"{PANEL_URL}/login"
        payload = f"username={PANEL_USERNAME}&password={PANEL_PASSWORD}"
        try:
            async with session.post(
                login_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                print(f"    Status : {resp.status}")
                print(f"    Content-Type: {resp.headers.get('Content-Type', '-')}")
                body = await resp.text()
                print(f"    Body   : {body[:400]}")
                cookies = {k: v.value for k, v in session.cookie_jar.filter_cookies(login_url).items()}
                print(f"    Cookies after login: {cookies}\n")
        except Exception as e:
            print(f"    ERROR: {e}\n")
            return

        # ---- Step 3: GET /xui/API/inbounds ----
        print("[3] GET /xui/API/inbounds...")
        api_url = f"{PANEL_URL}/xui/API/inbounds"
        try:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                print(f"    Status : {resp.status}")
                body = await resp.text()
                try:
                    parsed = json.loads(body)
                    print(f"    Success: {parsed.get('success')}")
                    objs = parsed.get('obj', [])
                    print(f"    Inbounds count: {len(objs)}")
                    for ib in objs:
                        print(f"      - ID {ib.get('id')}: {ib.get('remark','?')} [{ib.get('protocol','?')}] :{ib.get('port','?')}")
                except Exception:
                    print(f"    Body: {body[:300]}")
        except Exception as e:
            print(f"    ERROR: {e}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(diagnose())
