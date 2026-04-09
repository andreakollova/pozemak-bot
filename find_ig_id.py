#!/usr/bin/env python3
"""Diagnostic script to find your Instagram Business Account ID.
Run: python find_ig_id.py
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
if not TOKEN:
    print("ERROR: INSTAGRAM_ACCESS_TOKEN not set in .env")
    exit(1)

BASE = "https://graph.facebook.com/v21.0"


def get(path, **params):
    params["access_token"] = TOKEN
    r = httpx.get(f"{BASE}/{path}", params=params)
    return r.status_code, r.json()


print("=== 1. Token debug info ===")
code, data = get("me", fields="id,name,email")
print(f"  {code}: {data}\n")

print("=== 2. Pages I manage ===")
code, data = get("me/accounts", fields="id,name,access_token,instagram_business_account")
if code != 200:
    print(f"  ERROR {code}: {data}")
else:
    pages = data.get("data", [])
    print(f"  Found {len(pages)} page(s)")
    for p in pages:
        ig = p.get("instagram_business_account", {})
        ig_id = ig.get("id") if ig else None
        print(f"  Page: {p['name']} (id={p['id']})")
        print(f"    → instagram_business_account: {ig_id or 'NOT FOUND'}")

print()
print("=== 3. Try Page token directly on Page 1067932656400909 ===")
# Try with user token first
for fields in [
    "instagram_business_account",
    "instagram_business_account{id,name,username}",
    "connected_instagram_account",
    "connected_instagram_account{id,name,username}",
]:
    code, data = get("1067932656400909", fields=fields)
    print(f"  fields={fields!r}: {code}: {data}")

print()
print("=== 4. Check if we have a Page token in /me/accounts and use that ===")
code, data = get("me/accounts")
if code == 200:
    for p in data.get("data", []):
        if p["id"] == "1067932656400909":
            page_token = p.get("access_token", "")
            print(f"  Got Page token for {p['name']}: {page_token[:30]}...")
            # Try with the Page token
            r = httpx.get(
                f"{BASE}/1067932656400909",
                params={
                    "fields": "instagram_business_account{id,name,username}",
                    "access_token": page_token,
                },
            )
            print(f"  With Page token → {r.status_code}: {r.json()}")
            break
    else:
        print("  Page 1067932656400909 not found in /me/accounts")
