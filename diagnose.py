#!/usr/bin/env python3
"""
Diagnostic script - tries multiple login methods and shows raw responses.
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


async def try_login(session, method_name, **kwargs):
    url = URL + "/login"
    print(f"\n  [{method_name}] POST {url}")
    try:
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=10), **kwargs) as resp:
            raw = await resp.text()
            print(f"  Status : {resp.status}")
            print(f"  CT     : {resp.headers.get('Content-Type', '-')}")
            print(f"  Body   : '{raw[:300]}'")
            return resp.status == 200 and raw
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


async def diagnose():
    print(f"\n{'='*60}")
    print(f"URL  : {URL}")
    print(f"User : {USER}")
    print(f"{'='*60}")

    jar = aiohttp.CookieJar(unsafe=True)
    conn = aiohttp.TCPConnector(ssl=False)
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": URL,
        "Referer": URL + "/",
    }

    async with aiohttp.ClientSession(cookie_jar=jar, connector=conn, headers=hdrs) as session:

        print("\n[1] GET / to plant session cookie...")
        async with session.get(URL + "/", timeout=aiohttp.ClientTimeout(total=10)) as resp:
            print(f"  Status : {resp.status}")
            cookies = {k: v.value[:50] for k, v in jar.filter_cookies(URL).items()}
            print(f"  Cookies: {cookies}")
            await resp.read()

        print("\n[2] Login attempts:")

        # Method A: JSON
        await try_login(session, "JSON",
            json={"username": USER, "password": PASS},
            headers={"Content-Type": "application/json"}
        )

        # Method B: form-urlencoded string
        await try_login(session, "FORM-STR",
            data=f"username={USER}&password={PASS}",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Method C: dict (aiohttp encodes as form)
        await try_login(session, "FORM-DICT",
            data={"username": USER, "password": PASS}
        )

        # Method D: no content-type override
        await try_login(session, "BARE-JSON",
            json={"username": USER, "password": PASS}
        )

        print(f"\n{'='*60}")
        print("\n[3] Check curl command to run on the SERVER:")
        print(f"""curl -k -v -c /tmp/cookie.txt -X GET '{URL}/' && \\
curl -k -v -b /tmp/cookie.txt -X POST '{URL}/login' \\
  -H 'Content-Type: application/json' \\
  -d '{{"username":"{USER}","password":"{PASS}"}}'
""")


if __name__ == "__main__":
    asyncio.run(diagnose())
