import logging
from typing import Any

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import auth, credentials
    _firebase_available = True
except ImportError:
    firebase_admin = None
    auth = None
    credentials = None
    _firebase_available = False
    logger.warning("firebase-admin is not installed. Run: pip install firebase-admin")

_firebase_initialized = False


def init_firebase() -> None:
    global _firebase_initialized

    if _firebase_initialized:
        return

    if not _firebase_available:
        logger.error("Firebase package not installed.")
        return

    if not settings.firebase_credentials_path:
        logger.error("FIREBASE_CREDENTIALS_PATH is not set in your .env file.")
        return

    try:
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("Firebase initialized successfully.")
    except Exception as e:
        logger.error(f"Firebase initialization failed: {e}")


def verify_firebase_token(firebase_token: str) -> dict[str, Any]:
    init_firebase()

    if not _firebase_initialized or auth is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firebase is not configured on the server. Contact support.",
        )

    try:
        decoded = auth.verify_id_token(firebase_token)
        return {
            "uid":   decoded.get("uid", ""),
            "email": decoded.get("email") or None,
            "name":  decoded.get("name") or None,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase token."
        ) from exc




