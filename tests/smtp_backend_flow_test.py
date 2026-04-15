import argparse
import base64
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

# Allow running this script directly via "python tests/smtp_backend_flow_test.py".
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import Event, NotificationLog, Property, User
from app.models.entities import NotificationChannel
from app.utils.security import create_access_token


def _score_for_level(level: str) -> float:
    if level == "authorized":
        return 85.0
    if level == "unknown":
        return 60.0
    return 40.0


def _create_owner_user(email: str | None = None) -> tuple[int, str]:
    db = SessionLocal()
    try:
        stamp = int(time.time() * 1000)
        user = User(
            firebase_uid=f"smtp-test-{stamp}",
            email=email or f"smtp-test-{stamp}@example.com",
            full_name="SMTP Test Owner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token(str(user.id))
        return user.id, token
    finally:
        db.close()


def _print_event_and_notification_summary(event_id: int) -> tuple[bool, bool]:
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        if not event:
            print(f"Event {event_id} was not created.")
            return False, False

        logs = db.scalars(
            select(NotificationLog).where(NotificationLog.event_id == event_id).order_by(NotificationLog.id.asc())
        ).all()

        print(f"Event created: id={event.id}, status={event.ai_status.value}, score={event.similarity_score}")
        print(f"Notification logs found: {len(logs)}")

        has_email = False
        email_sent = False
        for log in logs:
            print(
                f" - channel={log.channel.value}, status={log.status.value}, detail={log.detail or ''}"
            )
            if log.channel == NotificationChannel.EMAIL:
                has_email = True
                if log.status.value == "sent":
                    email_sent = True

        return has_email, email_sent
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise SMTP through backend webhook notification flow")
    parser.add_argument(
        "--level",
        choices=["intruder", "unknown", "authorized"],
        default="intruder",
        help="Event level to simulate",
    )
    parser.add_argument(
        "--owner-email",
        default=None,
        help="Optional owner email for the seeded user. Defaults to generated address.",
    )
    args = parser.parse_args()

    if not settings.smtp_enabled:
        print("SMTP_ENABLED is false. Set SMTP_ENABLED=true in .env before running this test.")
        return 1

    user_id, access_token = _create_owner_user(args.owner_email)
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    client = TestClient(app)

    prop_resp = client.post(
        f"/api/v1/users/{user_id}/properties",
        json={"name": f"SMTP Test Property {int(time.time())}", "address": "SMTP Test Street"},
        headers=auth_headers,
    )
    if prop_resp.status_code != 200:
        print(f"Property creation failed: {prop_resp.status_code} {prop_resp.text}")
        return 2

    pid = prop_resp.json()["id"]

    snapshot = base64.b64encode(b"smtp-backend-test-image").decode("utf-8")
    webhook_resp = client.post(
        "/api/v1/webhooks/intruder",
        json={
            "property_id": pid,
            "similarity_score": _score_for_level(args.level),
            "snapshot_base64": snapshot,
            "person_name": "Known Person" if args.level == "authorized" else None,
            "note": f"smtp-backend-flow-{args.level}",
        },
        headers={"X-Webhook-Api-Key": settings.webhook_api_key},
    )
    if webhook_resp.status_code != 200:
        print(f"Webhook call failed: {webhook_resp.status_code} {webhook_resp.text}")
        return 3

    event_id = webhook_resp.json()["event_id"]
    print(f"Webhook accepted, event_id={event_id}")

    event_resp = client.get(f"/api/v1/users/{user_id}/properties/{pid}/events/{event_id}", headers=auth_headers)
    if event_resp.status_code != 200:
        print(f"Event retrieval failed: {event_resp.status_code} {event_resp.text}")
        return 4

    payload = event_resp.json()
    print(
        "Event detail OK: "
        f"status={payload.get('ai_status')}, has_snapshot_base64={bool(payload.get('snapshot_base64'))}"
    )

    has_email_log, email_sent = _print_event_and_notification_summary(event_id)
    if not has_email_log:
        print("No EMAIL notification log recorded. Check SMTP_ENABLED and owner email.")
        return 5
    if not email_sent:
        print("EMAIL log exists but status is not sent. Check SMTP credentials and provider settings.")
        return 6

    print("SMTP backend flow test passed: email channel recorded as sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
