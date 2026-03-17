import importlib
from typing import Any

from fastapi import HTTPException, status

from app.config import settings

firebase_admin = None
auth = None
credentials = None


_firebase_initialized = False


def init_firebase() -> None:
    global _firebase_initialized
    global firebase_admin, auth, credentials

    if _firebase_initialized or not settings.firebase_credentials_path:
        return
    try:
        firebase_admin = importlib.import_module("firebase_admin")
        auth = importlib.import_module("firebase_admin.auth")
        credentials = importlib.import_module("firebase_admin.credentials")
    except Exception:
        return

    cred = credentials.Certificate(settings.firebase_credentials_path)
    firebase_admin.initialize_app(cred)
    _firebase_initialized = True


def verify_firebase_token(firebase_token: str) -> dict[str, Any]:
    init_firebase()

    if _firebase_initialized and auth is not None:
        try:
            decoded = auth.verify_id_token(firebase_token)
            return {
                "uid": decoded.get("uid", ""),
                "email": decoded.get("email", ""),
                "name": decoded.get("name", "Unknown User"),
            }
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Firebase token") from exc

    if firebase_token.startswith("demo:"):
        # Development fallback: demo:<uid>:<email>:<name>
        parts = firebase_token.split(":", 3)
        if len(parts) == 4:
            return {"uid": parts[1], "email": parts[2], "name": parts[3]}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Firebase is not configured. Provide credentials or use demo token format demo:<uid>:<email>:<name>",
    )
