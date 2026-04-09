import httpx, os
from dotenv import load_dotenv
load_dotenv()

APP_ID = "718878481312398"
APP_SECRET = "a4b3b219f66a854175eb9a8f5326ce46"
SHORT_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
BASE = "https://graph.facebook.com/v21.0"

# Step 1: exchange short-lived user token → long-lived user token (60 days)
r = httpx.get(f"{BASE}/oauth/access_token", params={
    "grant_type": "fb_exchange_token",
    "client_id": APP_ID,
    "client_secret": APP_SECRET,
    "fb_exchange_token": SHORT_TOKEN,
})
print("Step 1:", r.status_code, r.json())
ll_user_token = r.json().get("access_token", "")

if not ll_user_token:
    print("FAILED — could not get long-lived user token")
    exit(1)

# Step 2: get long-lived Page token via /me/accounts
r2 = httpx.get(f"{BASE}/me/accounts", params={"access_token": ll_user_token})
print("Step 2:", r2.status_code, r2.json())

page_token = ""
for page in r2.json().get("data", []):
    print(f"  Page: {page['name']} (id={page['id']})")
    if page["id"] == "1029535373583219":
        page_token = page.get("access_token", "")

if page_token:
    print(f"\nLong-lived Page token (60 days):\n{page_token}")
else:
    print("FAILED — page token not found")
