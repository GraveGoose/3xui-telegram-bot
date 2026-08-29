#!/usr/bin/env python3
"""
Diagnostic: manually extracts Set-Cookie and injects it.
Run: python diagnose.py
"""
import asyncio
import aiohttp
import json
import os
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("PANEL_URL", "").rstrip("/")
USER = os.getenv("PANEL_USERNAME", "")
PASS = os.getenv("PANEL_PASSWORD", "")


async def diagnose():
    print(f"\n{'='*60}")
    print(f"URL: {URL}  User: {USER}")
    print(f"{'='*60}")

    conn = aiohttp.TCPConnector(ssl=False)
    # DummyCookieJar - disable automatic cookie handling
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.DummyCookieJar(),
        connector=conn,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        },
    ) as session:

        # Step 1: GET root, read Set-Cookie manually
        print("\n[1] GET / (manual cookie extraction)")
        cookie_val = ""
        async with session.get(URL + "/", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            print(f"  Status     : {resp.status}")
            raw_sc = resp.headers.get("Set-Cookie", "")
            print(f"  Set-Cookie : {raw_sc[:120]}")
            if raw_sc:
                cookie_val = raw_sc.split(";")[0].strip()
                print(f"  Extracted  : {cookie_val[:80]}")
            else:
                print("  WARNING: No Set-Cookie in response!")
            await resp.read()

        # Step 2: POST /login with manual Cookie header
        print("\n[2] POST /login (injecting cookie manually)")
        hdrs = {
            "Content-Type": "application/json",
            "Referer": URL + "/",
            "Origin": URL,
        }
        if cookie_val:
            hdrs["Cookie"] = cookie_val
            print(f"  Sending Cookie: {cookie_val[:80]}")
        else:
            print("  No cookie to send!")

        async with session.post(
            URL + "/login",
            json={"username": USER, "password": PASS},
            headers=hdrs,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            print(f"  Status : {resp.status}")
            print(f"  CT     : {resp.headers.get('Content-Type', '-')}")
            raw = await resp.text()
            print(f"  Body   : {raw[:400]}")
            new_sc = resp.headers.get("Set-Cookie", "")
            if new_sc:
                cookie_val = new_sc.split(";")[0].strip()
                print(f"  New cookie: {cookie_val[:80]}")

        # Step 3: GET /xui/API/inbounds
        if cookie_val:
            print("\n[3] GET /xui/API/inbounds")
            async with session.get(
                URL + "/xui/API/inbounds",
                headers={"Cookie": cookie_val},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                print(f"  Status : {resp.status}")
                raw = await resp.text()
                try:
                    data = json.loads(raw)
                    print(f"  Success: {data.get('success')}")
                    for ib in data.get("obj", []):
                        print(f"    ID={ib['id']} {ib.get('remark','?')} [{ib.get('protocol','?')}] :{ib.get('port','?')}")
                except Exception:
                    print(f"  Body: {raw[:300]}")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    asyncio.run(diagnose())
