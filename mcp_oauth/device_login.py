#!/usr/bin/env python
"""
Helper: start MCP device flow, print verification URL, poll until approved.

Usage (from backend/):
  python mcp_oauth/device_login.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body)
        except Exception:
            return {"error": body, "status": e.code}


def main():
    print(f"Requesting device code from {BASE} …")
    start = post("/mcp/oauth/device/code", {"client_id": "cursor"})
    if "device_code" not in start:
        print("Failed:", start)
        sys.exit(1)

    print()
    print("Open this URL and sign in:")
    print(" ", start.get("verification_uri_complete") or start["verification_uri"])
    print(" User code:", start["user_code"])
    print()
    print("Waiting for approval …")

    device_code = start["device_code"]
    interval = int(start.get("interval") or 5)
    while True:
        time.sleep(interval)
        tok = post(
            "/mcp/oauth/token",
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
        )
        err = tok.get("error")
        if err == "authorization_pending":
            print(".", end="", flush=True)
            continue
        if err:
            print("\nError:", tok)
            sys.exit(1)
        print("\n\nAccess token (paste into Cursor mcp.json):")
        print(tok["access_token"])
        print("\nScopes:", tok.get("scope"))
        return


if __name__ == "__main__":
    main()
