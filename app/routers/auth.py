from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.dependencies import get_db_session, get_current_user
from app.models import User
from app.models.entities import UserConsent
from app.schemas.schemas import RefreshTokenRequest, TokenResponse, VerifyTokenRequest
from app.services.file_service import remove_dir_if_exists, remove_file_if_exists
from app.services.firebase_service import verify_firebase_token
from app.utils.security import create_access_token, create_refresh_token, decode_refresh_token
from app.config import settings

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
        if not payload.consent_accepted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must accept the privacy policy to create an account."
            )
        user = User(
            firebase_uid=identity["uid"],
            email=identity.get("email"),
            full_name=identity.get("name") or "Unknown User",
        )
        db.add(user)
        db.flush()
        db.add(UserConsent(user_id=user.id, consent_type="privacy_policy", accepted=True))
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
    return TokenResponse(user_id=user.id, access_token=token, refresh_token=refresh_token)


@router.post("/revoke-consent")
def revoke_consent(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    try:
        # Anonymize consent records — nullify user_id and record revocation time
        db.execute(
            update(UserConsent)
            .where(UserConsent.user_id == current_user.id)
            .values(user_id=None, revoked_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        db.flush()

        # Delete all user files and data
        for property_obj in current_user.properties:
            for person in property_obj.persons:
                for photo in person.photos:
                    remove_file_if_exists(photo.file_path)
            for event in property_obj.events:
                remove_file_if_exists(event.snapshot_path)
        remove_dir_if_exists(settings.storage_root_path / "persons" / str(current_user.id))

        db.delete(current_user)
        db.commit()
        return {"message": "Consent revoked. Your account and all associated data have been deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    return TokenResponse(user_id=user.id, access_token=new_access_token, refresh_token=new_refresh_token)