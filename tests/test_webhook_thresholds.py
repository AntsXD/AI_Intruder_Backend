import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Event, NotificationLog
from app.models.entities import NotificationChannel


@pytest.mark.parametrize(
    "score,expected_status",
    [
        (45.0, "intruder"),
        (60.0, "human_review"),
        (85.0, "authorized"),
    ],
)
def test_webhook_threshold_branches(client, webhook_headers, make_auth_headers, score: float, expected_status: str) -> None:
    user_id, headers = make_auth_headers()

    prop = client.post(
        f"/api/v1/users/{user_id}/properties",
        json={"name": "Main House", "address": "Demo Address"},
        headers=headers,
    )
    assert prop.status_code == 200
    pid = prop.json()["id"]

    hook = client.post(
        "/api/v1/webhooks/intruder",
        json={
            "property_id": pid,
            "similarity_score": score,
            "snapshot_base64": "dGVzdA==",
            "note": "threshold test",
        },
        headers=webhook_headers,
    )
    assert hook.status_code == 200
    event_id = hook.json()["event_id"]

    event = client.get(f"/api/v1/users/{user_id}/properties/{pid}/events/{event_id}", headers=headers)
    assert event.status_code == 200
    assert event.json()["ai_status"] == expected_status

    db = SessionLocal()
    try:
        event_row = db.get(Event, event_id)
        assert event_row is not None
        telegram_logs = db.scalars(
            select(NotificationLog).where(
                NotificationLog.event_id == event_id,
                NotificationLog.channel == NotificationChannel.TELEGRAM,
            )
        ).all()
        assert telegram_logs == []
    finally:
        db.close()
