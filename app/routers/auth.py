from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db_session
from app.models import User
from app.schemas.schemas import RefreshTokenRequest, TokenResponse, VerifyTokenRequest
from app.services.firebase_service import verify_firebase_token
from app.utils.security import create_access_token, create_refresh_token, decode_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/verify-token", response_model=TokenResponse)
def verify_token(payload: VerifyTokenRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    identity = verify_firebase_token(payload.firebase_token)

    user = db.scalar(select(User).where(User.firebase_uid == identity["uid"]))
    if not user:
        user = User(
            firebase_uid=identity["uid"],
            email=identity.get("email") or f"{identity['uid']}@example.local",
            full_name=identity.get("name") or "Unknown User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshTokenRequest) -> TokenResponse:
    user_id = decode_refresh_token(payload.refresh_token)
    token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    return TokenResponse(access_token=token, refresh_token=refresh_token)
