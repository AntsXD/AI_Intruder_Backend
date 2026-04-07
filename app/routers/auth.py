from fastapi import APIRouter, Depends
from fastapi import HTTPException, status
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
    # Guard :reject identity with no email before touching the database
    if not identity.get("email"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An email address is required to use this app."
        )

    user = db.scalar(select(User).where(User.firebase_uid == identity["uid"]))
    if not user:
        user = User(
            firebase_uid=identity["uid"],
            email=identity.get("email"),
            full_name=identity.get("name") or "Unknown User",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        updated = False
        # Keep backend profile in sync with Firebase identity claims.
        if identity.get("email") and user.email != identity["email"]:
            user.email = identity["email"]
            updated = True
        if identity.get("name") and user.full_name != identity["name"]:
            user.full_name = identity["name"]
            updated = True
        if updated:
            db.commit()
            db.refresh(user)

    token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    return TokenResponse(access_token=token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    try:
        user_id = decode_refresh_token(payload.refresh_token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    user = db.get(User, int(user_id)) if user_id.isdigit() else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found for refresh token",
        )
    new_access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)
    return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token)