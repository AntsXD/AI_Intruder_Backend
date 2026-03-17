import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User


@pytest.fixture(autouse=True)
def isolated_db() -> None:
    # Keep tests deterministic by resetting schema for each test.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def webhook_headers() -> dict[str, str]:
    # Disable optional signed-mode checks during tests unless explicitly tested.
    settings.webhook_signing_secret = ""
    return {"X-Webhook-Api-Key": settings.webhook_api_key}


@pytest.fixture
def make_auth_headers(client: TestClient):
    def _make(uid: str = "demo-user") -> tuple[int, dict[str, str]]:
        response = client.post(
            "/api/v1/auth/verify-token",
            json={"firebase_token": f"demo:{uid}:{uid}@example.com:Demo User"},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]

        db = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.firebase_uid == uid))
            assert user is not None
            return user.id, {"Authorization": f"Bearer {token}"}
        finally:
            db.close()

    return _make
