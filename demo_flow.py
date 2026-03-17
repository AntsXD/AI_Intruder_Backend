import json

from fastapi.testclient import TestClient

from app.config import settings
from app.database import Base, engine
from app.main import app


def pretty(label: str, payload: dict) -> None:
    print(f"\n[{label}]")
    print(json.dumps(payload, indent=2))


def main() -> None:
    # Reset schema for a deterministic demo run.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    client = TestClient(app)

    auth = client.post(
        "/api/v1/auth/verify-token",
        json={"firebase_token": "demo:owner-1:owner@example.com:Owner One"},
    )
    auth.raise_for_status()
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    pretty("auth", auth.json())

    user = client.get("/api/v1/users/1", headers=headers)
    user.raise_for_status()
    user_id = user.json()["id"]
    pretty("user", user.json())

    prop = client.post(
        f"/api/v1/users/{user_id}/properties",
        json={"name": "Main Home", "address": "Demo Street"},
        headers=headers,
    )
    prop.raise_for_status()
    pid = prop.json()["id"]
    pretty("property", prop.json())

    person = client.post(
        f"/api/v1/users/{user_id}/properties/{pid}/persons",
        json={"name": "Allowed Person"},
        headers=headers,
    )
    person.raise_for_status()
    person_id = person.json()["id"]
    pretty("person", person.json())

    fake_jpg = b"\xff\xd8\xff\xe0demo-image-content\xff\xd9"
    for idx in range(3):
        upload = client.post(
            f"/api/v1/users/{user_id}/properties/{pid}/persons/{person_id}/photos",
            params={"is_display": idx == 0},
            files={"file": (f"face_{idx}.jpg", fake_jpg, "image/jpeg")},
            headers=headers,
        )
        upload.raise_for_status()
        pretty(f"photo_{idx}", upload.json())

    activate = client.post(
        f"/api/v1/users/{user_id}/properties/{pid}/persons/{person_id}/activate",
        headers=headers,
    )
    activate.raise_for_status()
    pretty("activate_person", activate.json())

    camera = client.put(
        f"/api/v1/users/{user_id}/properties/{pid}/camera-feed",
        json={
            "source_url": "https://example.com/fake-stream.m3u8",
            "stream_type": "external_hls",
            "is_enabled": True,
        },
        headers=headers,
    )
    camera.raise_for_status()
    pretty("camera_feed", camera.json())

    hook_headers = {"X-Webhook-Api-Key": settings.webhook_api_key}

    for score in [45.0, 60.0, 85.0]:
        event = client.post(
            "/api/v1/webhooks/intruder",
            json={"property_id": pid, "similarity_score": score, "note": f"score={score}"},
            headers=hook_headers,
        )
        event.raise_for_status()
        pretty(f"webhook_{score}", event.json())

    events = client.get(f"/api/v1/users/{user_id}/properties/{pid}/events", headers=headers)
    events.raise_for_status()
    pretty("events", {"count": len(events.json()), "items": events.json()})

    human_event = next((e for e in events.json() if e["status"] == "human_review"), None)
    if human_event:
        verify = client.post(
            f"/api/v1/users/{user_id}/properties/{pid}/events/{human_event['id']}/verify",
            json={"confirmed_intruder": True},
            headers=headers,
        )
        verify.raise_for_status()
        pretty("verify_human_review", verify.json())

    print("\nDemo flow completed successfully.")


if __name__ == "__main__":
    main()
