"""
FCM End-to-End Test Script
==========================
Tests the full push notification flow:
  1. Sign in via Firebase REST API  →  get a Firebase ID token
  2. Exchange Firebase token for a backend JWT  (POST /auth/verify-token)
  3. Register a real FCM device token         (POST /users/{id}/devices/fcm-token)
  4. Trigger a webhook event                  (POST /webhooks/intruder)
  5. Verify the notification was logged       (GET  /users/{id}/properties/{pid}/events/{eid})

SETUP
-----
1. In your .env set:
       FCM_ENABLED=true
       FIREBASE_CREDENTIALS_PATH=./your-firebase-adminsdk.json
       FIREBASE_WEB_API_KEY=<your Firebase Web API key>
       FIREBASE_TEST_EMAIL=<a test user email in your Firebase project>
       FIREBASE_TEST_PASSWORD=<that user's password>

2. Set FCM_TOKEN below to a real FCM registration token from your mobile/web app.
   (Run the app, log the token from FirebaseMessaging.getInstance().getToken(), paste it here.)

3. Make sure the server is running:
       uvicorn app.main:app --reload

4. Run:
       python test_fcm.py
"""

import json
import sqlite3
import sys
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# Get the directory where this script is located (backend folder)
SCRIPT_DIR = Path(__file__).parent

# ─── Configuration ────────────────────────────────────────────────────────────
BASE_URL        = "http://127.0.0.1:8000/api/v1"
WEBHOOK_API_KEY = os.getenv("WEBHOOK_API_KEY", "CHANGE_ME_WEBHOOK_KEY")

# Firebase credentials for getting a real ID token
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "")
TEST_EMAIL       = os.getenv("FIREBASE_TEST_EMAIL", "")
TEST_PASSWORD    = os.getenv("FIREBASE_TEST_PASSWORD", "")

# Paste a real FCM registration token from your device/app here:
FCM_TOKEN = os.getenv("FCM_TEST_TOKEN", "PASTE_YOUR_FCM_TOKEN_HERE")

# A 1×1 transparent PNG (valid base64 snapshot placeholder)
DUMMY_SNAPSHOT = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
# ──────────────────────────────────────────────────────────────────────────────

PASS = "\033[92m✔\033[0m"
FAIL = "\033[91m✘\033[0m"


def step(label: str):
    print(f"\n{'─'*60}\n  {label}\n{'─'*60}")


def ok(msg: str):
    print(f"  {PASS} {msg}")


def fail(msg: str, resp: requests.Response | None = None):
    print(f"  {FAIL} {msg}")
    if resp is not None:
        print(f"     Status : {resp.status_code}")
        try:
            print(f"     Body   : {json.dumps(resp.json(), indent=4)}")
        except Exception:
            print(f"     Body   : {resp.text}")
    sys.exit(1)


# ─── Step 1: Get Firebase ID token ────────────────────────────────────────────
step("1 / 5  →  Sign in via Firebase REST API")

if not FIREBASE_WEB_API_KEY:
    fail("FIREBASE_WEB_API_KEY is not set. Add it to your .env file.")
if not TEST_EMAIL or not TEST_PASSWORD:
    fail("FIREBASE_TEST_EMAIL / FIREBASE_TEST_PASSWORD are not set in .env.")

firebase_signin_url = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    f"?key={FIREBASE_WEB_API_KEY}"
)
resp = requests.post(firebase_signin_url, json={
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
    "returnSecureToken": True,
})
if resp.status_code != 200:
    fail("Firebase sign-in failed", resp)

firebase_id_token = resp.json()["idToken"]
ok(f"Firebase ID token obtained (first 40 chars): {firebase_id_token[:40]}…")


# ─── Step 2: Exchange Firebase token for backend JWT ──────────────────────────
step("2 / 5  →  Exchange Firebase token for backend JWT")

resp = requests.post(f"{BASE_URL}/auth/verify-token", json={
    "firebase_token": firebase_id_token,
    "consent_accepted": True,
})
if resp.status_code != 200:
    fail("verify-token failed", resp)

data     = resp.json()
user_id  = data["user_id"]
jwt      = data["access_token"]
headers  = {"Authorization": f"Bearer {jwt}"}
ok(f"Logged in as user_id={user_id}")


# ─── Step 3: Register FCM device token ────────────────────────────────────────
step("3 / 5  →  Register FCM device token")

if FCM_TOKEN == "PASTE_YOUR_FCM_TOKEN_HERE":
    print("  ⚠  FCM_TOKEN is not set — skipping token registration.")
    print("     Set FCM_TEST_TOKEN in your .env or edit FCM_TOKEN in this script.")
    FCM_TOKEN_REGISTERED = False
else:
    resp = requests.post(
        f"{BASE_URL}/users/{user_id}/devices/fcm-token",
        headers=headers,
        json={"token": FCM_TOKEN, "device_name": "test-script"},
    )
    if resp.status_code != 200:
        fail("FCM token registration failed", resp)
    ok(f"FCM token registered: {FCM_TOKEN[:40]}…")
    FCM_TOKEN_REGISTERED = True


# ─── Step 4: Create a property (needed if you don't have one yet) ─────────────
step("4a / 5  →  Ensure a test property exists")

resp = requests.get(f"{BASE_URL}/users/{user_id}/properties", headers=headers)
if resp.status_code != 200:
    fail("Could not fetch properties", resp)

properties = resp.json()
if properties:
    property_id = properties[0]["id"]
    ok(f"Using existing property id={property_id}  ({properties[0]['name']})")
else:
    resp = requests.post(
        f"{BASE_URL}/users/{user_id}/properties",
        headers=headers,
        json={"name": "FCM Test Property", "address": "123 Test St"},
    )
    if resp.status_code != 200:
        fail("Could not create test property", resp)
    property_id = resp.json()["id"]
    ok(f"Created new property id={property_id}")


# ─── Step 5: Trigger the intruder webhook ─────────────────────────────────────
step("4b / 5  →  Trigger intruder webhook (similarity=0.1 → intruder)")

resp = requests.post(
    f"{BASE_URL}/webhooks/intruder",
    headers={"x-webhook-api-key": WEBHOOK_API_KEY},
    json={
        "property_id": property_id,
        "similarity_score": 0.1,          # low score → intruder
        "snapshot_base64": DUMMY_SNAPSHOT,
        "note": "FCM test event",
    },
)
if resp.status_code != 200:
    fail("Webhook call failed", resp)

event_id     = resp.json()["event_id"]
event_status = resp.json()["status"]
ok(f"Event created: id={event_id}  status={event_status}")


# ─── Step 6: Check notification logs directly from SQLite ─────────────────────
step("5 / 5  →  Check notification result")

# The webhook fires notifications in a background task — give it a moment.
print("  ⏳ Waiting 3 seconds for background notification task…")
time.sleep(3)

# Parse DATABASE_URL to get the actual database file path
db_url = os.getenv("DATABASE_URL", "sqlite:///./intruder_demo.db")
if db_url.startswith("sqlite:///"):
    db_filename = db_url.replace("sqlite:///", "")
else:
    db_filename = "intruder_demo.db"

# Make path absolute, relative to script directory
DB_PATH = str(SCRIPT_DIR / db_filename)

try:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT channel, status, detail, created_at FROM notification_logs WHERE event_id = ? ORDER BY id",
        (event_id,),
    ).fetchall()
    conn.close()
except Exception as e:
    print(f"  ⚠  Could not read notification_logs: {e}")
    rows = []

if not rows:
    print(f"  {FAIL} No notification log entries found for event {event_id}.")
    if not FCM_TOKEN_REGISTERED:
        print("     FCM token was not registered — no push was attempted.")
    else:
        print("     The background task may not have run. Check your server is running.")
else:
    print(f"  Found {len(rows)} notification log(s):\n")
    for r in rows:
        ch      = r["channel"]
        st      = r["status"]
        detail  = r["detail"] or ""
        emoji   = PASS if st.lower() == "sent" else FAIL
        print(f"    {emoji}  [{ch.upper():>8}]  {st.upper()}  —  {detail}")

    push_sent = any(r["channel"].lower() == "push" and r["status"].lower() == "sent" for r in rows)
    push_failed = any(r["channel"].lower() == "push" and r["status"].lower() == "failed" for r in rows)

    print()
    if push_sent:
        ok("FCM push notification was delivered successfully! 🎉")
    elif push_failed:
        print(f"  {FAIL} FCM push failed — check the detail above (likely an invalid token or credentials issue).")
    elif not FCM_TOKEN_REGISTERED:
        print("  ⚠  FCM token wasn't registered, so no push was attempted.")
    else:
        print("  ⚠  No PUSH log entry found — FCM may be disabled in .env (FCM_ENABLED=false).")


print(f"\n{'═'*60}")
print("  All steps completed.")
print(f"{'═'*60}\n")

