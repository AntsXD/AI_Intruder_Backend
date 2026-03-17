import hashlib
import hmac
import time

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.utils.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db


def require_webhook_api_key(x_webhook_api_key: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_webhook_api_key, settings.webhook_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook API key")


async def require_webhook_security(
    request: Request,
    x_webhook_api_key: str = Header(default=""),
    x_webhook_timestamp: str = Header(default=""),
    x_webhook_signature: str = Header(default=""),
) -> None:
    if not hmac.compare_digest(x_webhook_api_key, settings.webhook_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook API key")

    if not settings.webhook_signing_secret:
        return

    if not x_webhook_timestamp or not x_webhook_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing webhook signature headers")

    try:
        timestamp_int = int(x_webhook_timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook timestamp") from exc

    now = int(time.time())
    if abs(now - timestamp_int) > settings.webhook_signature_tolerance_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Webhook timestamp outside allowed window")

    body = await request.body()
    signed_bytes = x_webhook_timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(settings.webhook_signing_secret.encode("utf-8"), signed_bytes, hashlib.sha256).hexdigest()
    expected = f"sha256={digest}"

    if not hmac.compare_digest(x_webhook_signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, int(user_id)) if user_id.isdigit() else None
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def ensure_user_scope(path_user_id: int, current_user: User) -> None:
    if current_user.id != path_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
