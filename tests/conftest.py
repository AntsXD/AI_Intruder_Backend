import pytest
import requests
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


@pytest.fixture(scope="session")
def real_firebase_token() -> str:
    """
    Calls real Firebase once per test session and returns a real idToken.
    Requires FIREBASE_WEB_API_KEY, FIREBASE_TEST_EMAIL, FIREBASE_TEST_PASSWORD in .env
    """
    assert settings.firebase_web_api_key,   "FIREBASE_WEB_API_KEY is not set in .env"
    assert settings.firebase_test_email,    "FIREBASE_TEST_EMAIL is not set in .env"
    assert settings.firebase_test_password, "FIREBASE_TEST_PASSWORD is not set in .env"

    response = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={settings.firebase_web_api_key}",
        json={
            "email":             settings.firebase_test_email,
            "password":          settings.firebase_test_password,
            "returnSecureToken": True,
        },
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Could not get Firebase token.\n"
            f"Status: {response.status_code}\n"
            f"Detail: {response.json()}"
        )

    token = response.json()["idToken"]
    print(f"\n✅ Firebase token obtained for {settings.firebase_test_email}")
    return token


@pytest.fixture
def make_auth_headers(client: TestClient, real_firebase_token: str):
    """
    Exchanges the real Firebase token for your backend tokens,
    then returns the user id and auth headers ready to use in tests.
    """
    def _make() -> tuple[int, dict[str, str]]:
        response = client.post(
            "/api/v1/auth/verify-token",
            json={"firebase_token": real_firebase_token},
        )
        assert response.status_code == 200, (
            f"verify-token failed: {response.json()}"
        )

        token = response.json()["access_token"]

        db = SessionLocal()
        try:
            user = db.scalar(
                select(User).where(
                    User.email == settings.firebase_test_email
                )
            )
            assert user is not None, "User was not created in the database"
            return user.id, {"Authorization": f"Bearer {token}"}
        finally:
            db.close()

    return _make