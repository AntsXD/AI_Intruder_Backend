from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.orm import Session
import httpx

from app.dependencies import ensure_user_scope, get_current_user, get_db_session
from app.models import CameraStream, Property, StreamType, User
from app.schemas.schemas import CameraFeedOut, CameraFeedUpsertRequest
from app.services.stream_service import validate_stream_url_for_type
from app.utils.security import create_stream_access_token, decode_stream_access_token

router = APIRouter(tags=["streams"])


@router.put("/users/{user_id}/properties/{pid}/camera-feed", response_model=CameraFeedOut)
def upsert_camera_feed(
    user_id: int,
    pid: int,
    payload: CameraFeedUpsertRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CameraFeedOut:
    ensure_user_scope(user_id, current_user)

    property_obj = db.scalar(select(Property).where(and_(Property.id == pid, Property.user_id == user_id)))
    if not property_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    stream_type = StreamType(payload.stream_type)
    validate_stream_url_for_type(payload.source_url, stream_type)

    stream = db.scalar(select(CameraStream).where(CameraStream.property_id == pid))
    if not stream:
        stream = CameraStream(
            property_id=pid,
            source_url=payload.source_url,
            stream_type=stream_type,
            is_enabled=payload.is_enabled,
        )
        db.add(stream)
    else:
        stream.source_url = payload.source_url
        stream.stream_type = stream_type
        stream.is_enabled = payload.is_enabled

    db.commit()
    db.refresh(stream)

    token = create_stream_access_token(user_id=user_id, stream_id=stream.id)
    playback_url = str(request.url_for("play_camera_stream", stream_id=stream.id)) + f"?token={token}"

    return CameraFeedOut(
        property_id=pid,
        source_url=stream.source_url,
        stream_type=stream.stream_type.value,
        is_enabled=stream.is_enabled,
        playback_url=playback_url,
    )


@router.get("/users/{user_id}/properties/{pid}/camera-feed", response_model=CameraFeedOut)
def get_camera_feed(
    user_id: int,
    pid: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CameraFeedOut:
    ensure_user_scope(user_id, current_user)

    stream = db.scalar(
        select(CameraStream)
        .join(Property, Property.id == CameraStream.property_id)
        .where(and_(Property.id == pid, Property.user_id == user_id))
    )
    if not stream:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera feed not configured")

    token = create_stream_access_token(user_id=user_id, stream_id=stream.id)
    playback_url = str(request.url_for("play_camera_stream", stream_id=stream.id)) + f"?token={token}"

    return CameraFeedOut(
        property_id=pid,
        source_url=stream.source_url,
        stream_type=stream.stream_type.value,
        is_enabled=stream.is_enabled,
        playback_url=playback_url,
    )


@router.get("/streams/{stream_id}/play", name="play_camera_stream")
async def play_camera_stream(
    stream_id: int,
    token: str = Query(..., min_length=10),
    db: Session = Depends(get_db_session),
):
    token_payload = decode_stream_access_token(token)
    if token_payload["stream_id"] != stream_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid stream scope")

    stream = db.scalar(
        select(CameraStream)
        .join(Property, Property.id == CameraStream.property_id)
        .where(and_(CameraStream.id == stream_id, Property.user_id == token_payload["user_id"]))
    )
    if not stream or not stream.is_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream unavailable")

    if stream.stream_type in {StreamType.EXTERNAL_HLS, StreamType.EXTERNAL_WEBRTC}:
        return RedirectResponse(stream.source_url)

    async def stream_generator():
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            async with client.stream("GET", stream.source_url) as response:
                if response.status_code >= 400:
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to fetch camera feed")
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream_generator(), media_type="application/octet-stream")
