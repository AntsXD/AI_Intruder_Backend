import logging
from typing import Any

from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import auth, credentials, messaging
    _firebase_available = True
except ImportError:
    firebase_admin = None
    auth = None
    credentials = None
    messaging = None
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
        import os
        if not os.path.exists(settings.firebase_credentials_path):
            logger.error("Firebase credentials file does not exist at configured path.")
            return
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        logger.info("Firebase initialized successfully.")
    except Exception as e:
        logger.error(f"Firebase initialization failed: {e}")


def verify_firebase_token(firebase_token: str) -> dict[str, Any]:
    init_firebase()

    if not _firebase_initialized or auth is None:
        logger.error(f"Firebase not initialized. available={_firebase_available}, initialized={_firebase_initialized}, auth={auth}")
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
        logger.error(f"Firebase token verification failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase token."
        ) from exc


def send_fcm_notification(token: str, title: str, body: str, data: dict[str, str] | None = None) -> str:
    init_firebase()
    if not _firebase_initialized or messaging is None:
        raise RuntimeError("Firebase is not configured for FCM.")

    message = messaging.Message(
        token=token,
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
    )
    result = messaging.send(message)
    logger.info(f"FCM sent successfully: message_id={result}")
    return result





