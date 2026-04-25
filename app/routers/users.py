import base64
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.dependencies import ensure_user_scope, get_current_user, get_db_session
from app.models import Event, Person, PersonPhoto, Property, Protocol, ProtocolAssignment, User, UserConsent, UserDeviceToken
from app.models.entities import EventStatus
from app.schemas.schemas import (
    DeviceTokenDeleteRequest,
    DeviceTokenUpsertRequest,
    EventDetailOut,
    EventOut,
    PersonActivationResponse,
    PersonCreate,
    PersonOut,
    PersonPhotoOut,
    PersonUpdate,
    PropertyCreate,
    PropertyOut,
    PropertyUpdate,
    ProtocolCreate,
    ProtocolOut,
    UserOut,
    UserUpdate,
    VerifyEventRequest,
)
from app.config import settings
from app.protocols import SUPPORTED_PROTOCOL_NAMES
from app.services.file_service import remove_dir_if_exists, remove_file_if_exists, save_person_photo, to_storage_relative
from app.services.notification_service import run_owner_intruder_confirmation_task

router = APIRouter(prefix="/users", tags=["users"])


def _get_property_for_user(db: Session, user_id: int, property_id: int) -> Property:
    property_obj = db.scalar(select(Property).where(and_(Property.id == property_id, Property.user_id == user_id)))
    if not property_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return property_obj


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)) -> UserOut:
    ensure_user_scope(user_id, current_user)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> UserOut:
    ensure_user_scope(user_id, current_user)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.phone_number is not None:
        user.phone_number = payload.phone_number

    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/devices/fcm-token")
def upsert_fcm_token(
    user_id: int,
    payload: DeviceTokenUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    ensure_user_scope(user_id, current_user)
    row = db.scalar(select(UserDeviceToken).where(UserDeviceToken.token == payload.token))
    if not row:
        db.add(UserDeviceToken(user_id=user_id, token=payload.token, device_name=payload.device_name))
    else:
        row.user_id = user_id
        row.device_name = payload.device_name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"message": "FCM token saved"}


@router.delete("/{user_id}/devices/fcm-token")
def delete_fcm_token(
    user_id: int,
    payload: DeviceTokenDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    ensure_user_scope(user_id, current_user)
    row = db.scalar(select(UserDeviceToken).where(UserDeviceToken.user_id == user_id, UserDeviceToken.token == payload.token))
    if row:
        db.delete(row)
        db.commit()
    return {"message": "FCM token removed"}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    ensure_user_scope(user_id, current_user)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Anonymize consent records before deleting user
    db.execute(
        update(UserConsent)
        .where(UserConsent.user_id == user_id)
        .values(user_id=None, revoked_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    db.flush()

    # GDPR-friendly cleanup for filesystem artifacts owned by this user.
    for property_obj in user.properties:
        for person in property_obj.persons:
            for photo in person.photos:
                remove_file_if_exists(photo.file_path)
        for event in property_obj.events:
            remove_file_if_exists(event.snapshot_path)

    remove_dir_if_exists(settings.storage_root_path / "persons" / str(user_id))

    db.delete(user)
    db.commit()
    return {"message": "User and associated data deleted"}



@router.get("/{user_id}/properties", response_model=list[PropertyOut])
def list_properties(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[PropertyOut]:
    ensure_user_scope(user_id, current_user)
    rows = db.scalars(select(Property).where(Property.user_id == user_id).order_by(Property.id.desc())).all()
    return list(rows)


@router.post("/{user_id}/properties", response_model=PropertyOut)
def create_property(
    user_id: int,
    payload: PropertyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PropertyOut:
    ensure_user_scope(user_id, current_user)
    existing = db.scalar(select(Property).where(and_(Property.user_id == user_id, Property.name == payload.name)))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A property with this name already exists.")
    property_obj = Property(user_id=user_id, name=payload.name, address=payload.address)
    db.add(property_obj)
    db.commit()
    db.refresh(property_obj)
    return property_obj


@router.get("/{user_id}/properties/{pid}", response_model=PropertyOut)
def get_property(
    user_id: int,
    pid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PropertyOut:
    ensure_user_scope(user_id, current_user)
    return _get_property_for_user(db, user_id, pid)


@router.put("/{user_id}/properties/{pid}", response_model=PropertyOut)
def update_property(
    user_id: int,
    pid: int,
    payload: PropertyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PropertyOut:
    ensure_user_scope(user_id, current_user)
    property_obj = _get_property_for_user(db, user_id, pid)
    if payload.name is not None:
        property_obj.name = payload.name
    if payload.address is not None:
        property_obj.address = payload.address
    db.commit()
    db.refresh(property_obj)
    return property_obj


@router.delete("/{user_id}/properties/{pid}")
def delete_property(
    user_id: int,
    pid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    ensure_user_scope(user_id, current_user)
    property_obj = _get_property_for_user(db, user_id, pid)

    for person in property_obj.persons:
        for photo in person.photos:
            remove_file_if_exists(photo.file_path)
    for event in property_obj.events:
        remove_file_if_exists(event.snapshot_path)

    remove_dir_if_exists(settings.storage_root_path / "persons" / str(user_id) / str(pid))
    remove_dir_if_exists(settings.storage_root_path / "events" / str(pid))

    db.delete(property_obj)
    db.commit()
    return {"message": "Property deleted"}


@router.get("/{user_id}/properties/{pid}/persons", response_model=list[PersonOut])
def list_persons(
    user_id: int,
    pid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[PersonOut]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    rows = db.scalars(select(Person).where(Person.property_id == pid).order_by(Person.id.desc())).all()
    return list(rows)



@router.post("/{user_id}/properties/{pid}/persons", response_model=PersonOut)
def create_person(
    user_id: int,
    pid: int,
    payload: PersonCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PersonOut:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    person = Person(property_id=pid, name=payload.name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.get("/{user_id}/properties/{pid}/persons/{person_id}", response_model=PersonOut)
def get_person(
    user_id: int,
    pid: int,
    person_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PersonOut:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    person = db.scalar(select(Person).where(and_(Person.id == person_id, Person.property_id == pid)))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return person


@router.put("/{user_id}/properties/{pid}/persons/{person_id}", response_model=PersonOut)
def update_person(
    user_id: int,
    pid: int,
    person_id: int,
    payload: PersonUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PersonOut:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    person = db.scalar(select(Person).where(and_(Person.id == person_id, Person.property_id == pid)))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    if payload.name is not None:
        person.name = payload.name
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{user_id}/properties/{pid}/persons/{person_id}")
def delete_person(
    user_id: int,
    pid: int,
    person_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    person = db.scalar(select(Person).where(and_(Person.id == person_id, Person.property_id == pid)))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    was_active = person.is_active
    for photo in person.photos:
        remove_file_if_exists(photo.file_path)
    db.delete(person)
    db.commit()

    if settings.ai_service_url and was_active:
        try:
            with httpx.Client(timeout=10) as client:
                client.delete(
                    f"{settings.ai_service_url}/properties/{pid}/persons/{person_id}",
                    headers={"X-API-Key": settings.ai_service_api_key},
                )
        except Exception as exc:
            logger.warning("Failed to deregister person %d from AI: %s", person_id, exc)

    return {"message": "Person deleted"}


@router.post("/{user_id}/properties/{pid}/persons/{person_id}/activate", response_model=PersonActivationResponse)
def activate_person(
    user_id: int,
    pid: int,
    person_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> PersonActivationResponse:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)

    person = db.scalar(select(Person).where(and_(Person.id == person_id, Person.property_id == pid)))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    photo_count = db.scalar(select(func.count(PersonPhoto.id)).where(PersonPhoto.person_id == person_id)) or 0

    if photo_count != 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exactly 3 photos are required")

    person.is_active = True
    db.commit()

    # Notify AI service with base64-encoded photos
    if settings.ai_service_url:
        try:
            photos_payload = []
            for photo in person.photos:
                with open(photo.file_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                photos_payload.append({
                    "type": photo.photo_type or "unknown",
                    "data": encoded,
                })
            with httpx.Client(timeout=10) as client:
                client.post(
                    f"{settings.ai_service_url}/persons/register",
                    json={
                        "person_id": person.id,
                        "property_id": pid,
                        "photos": photos_payload,
                    },
                    headers={"X-API-Key": settings.ai_service_api_key},
                )
        except Exception as exc:
            logger.warning("Failed to notify AI service for person %d: %s", person.id, exc)

    return PersonActivationResponse(
        person_id=person.id,
        is_active=person.is_active,
        photo_count=photo_count,
        has_display_photo=True,
        message="Person activated for recognition",
    )


@router.get("/{user_id}/properties/{pid}/persons/{person_id}/photos", response_model=list[PersonPhotoOut])
def list_person_photos(
    user_id: int,
    pid: int,
    person_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[PersonPhoto]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    person = db.scalar(select(Person).where(and_(Person.id == person_id, Person.property_id == pid)))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return db.scalars(select(PersonPhoto).where(PersonPhoto.person_id == person_id)).all()


@router.post("/{user_id}/properties/{pid}/persons/{person_id}/photos")
async def upload_person_photo(
    user_id: int,
    pid: int,
    person_id: int,
    photo_type: Literal["face", "left_profile", "right_profile"],
    is_display: bool = False,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str | int]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    person = db.scalar(select(Person).where(and_(Person.id == person_id, Person.property_id == pid)))
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")

    count = db.scalar(select(func.count(PersonPhoto.id)).where(PersonPhoto.person_id == person_id))
    if count is not None and count >= 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A person can only have up to 3 photos")

    # Prevent duplicate photo types
    existing_type = db.scalar(
        select(PersonPhoto).where(
            and_(PersonPhoto.person_id == person_id, PersonPhoto.photo_type == photo_type)
        )
    )
    if existing_type:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A {photo_type} photo already exists for this person")

    path = await save_person_photo(user_id, pid, person_id, file)
    if is_display:
        for old in person.photos:
            old.is_display = False

    photo = PersonPhoto(person_id=person_id, file_path=path, photo_type=photo_type, is_display=is_display)
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return {"photo_id": photo.id, "file_path": to_storage_relative(photo.file_path), "photo_type": photo.photo_type}


@router.get("/{user_id}/properties/{pid}/persons/{person_id}/photos/{photo_id}")
def get_person_photo(
    user_id: int,
    pid: int,
    person_id: int,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> FileResponse:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)

    photo = db.scalar(
        select(PersonPhoto)
        .join(Person, Person.id == PersonPhoto.person_id)
        .where(and_(PersonPhoto.id == photo_id, PersonPhoto.person_id == person_id, Person.property_id == pid))
    )
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    if not photo.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo file path missing")

    if not Path(photo.file_path).is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo file not found on disk")

    return FileResponse(photo.file_path)


@router.delete("/{user_id}/properties/{pid}/persons/{person_id}/photos/{photo_id}")
def delete_person_photo(
    user_id: int,
    pid: int,
    person_id: int,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)

    photo = db.scalar(
        select(PersonPhoto)
        .join(Person, Person.id == PersonPhoto.person_id)
        .where(and_(PersonPhoto.id == photo_id, PersonPhoto.person_id == person_id, Person.property_id == pid))
    )
    if not photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    remove_file_if_exists(photo.file_path)
    db.delete(photo)
    db.commit()
    return {"message": "Photo deleted"}


@router.get("/{user_id}/properties/{pid}/protocols", response_model=list[ProtocolOut])
def list_protocols(
    user_id: int,
    pid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[ProtocolOut]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    rows = db.scalars(
        select(Protocol)
        .join(ProtocolAssignment, ProtocolAssignment.protocol_id == Protocol.id)
        .where(ProtocolAssignment.property_id == pid)
    ).all()
    return list(rows)


@router.put("/{user_id}/properties/{pid}/protocols", response_model=list[ProtocolOut])
def set_protocols(
    user_id: int,
    pid: int,
    payload: list[ProtocolCreate],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[ProtocolOut]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)

    existing_assignments = db.scalars(select(ProtocolAssignment).where(ProtocolAssignment.property_id == pid)).all()
    for assignment in existing_assignments:
        db.delete(assignment)

    result: list[Protocol] = []
    seen_names: set[str] = set()
    allowed_names = ", ".join(sorted(SUPPORTED_PROTOCOL_NAMES))
    for item in payload:
        protocol_name = item.name.strip()
        if protocol_name not in SUPPORTED_PROTOCOL_NAMES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported protocol '{protocol_name}'. Allowed values: {allowed_names}",
            )

        key = protocol_name.lower()
        if key in seen_names:
            continue
        seen_names.add(key)

        protocol = db.scalar(select(Protocol).where(Protocol.name == protocol_name))
        if not protocol:
            protocol = Protocol(
                name=protocol_name,
                description=item.description,
            )
            db.add(protocol)
            db.flush()
        else:
            protocol.description = item.description

        db.add(ProtocolAssignment(property_id=pid, protocol_id=protocol.id))
        result.append(protocol)

    db.commit()
    return result


@router.get("/{user_id}/properties/{pid}/events", response_model=list[EventOut])
def list_events(
    user_id: int,
    pid: int,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[EventOut]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)

    query = select(Event).where(Event.property_id == pid)
    if status_filter:
        try:
            parsed_status = EventStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status_filter") from exc
        query = query.where(Event.ai_status == parsed_status)
    rows = db.scalars(query.order_by(Event.id.desc()).limit(limit).offset(offset)).all()
    return list(rows)


@router.get("/{user_id}/properties/{pid}/events/{eid}", response_model=EventDetailOut)
def get_event(
    user_id: int,
    pid: int,
    eid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> EventDetailOut:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    event = db.scalar(select(Event).where(and_(Event.id == eid, Event.property_id == pid)))
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if not event.snapshot_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot path missing")

    snapshot_file = Path(event.snapshot_path)
    if not snapshot_file.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot file not found on disk")

    with open(snapshot_file, "rb") as f:
        snapshot_base64 = base64.b64encode(f.read()).decode("utf-8")

    return EventDetailOut(
        id=event.id,
        property_id=event.property_id,
        person_id=event.person_id,
        similarity_score=event.similarity_score,
        ai_status=event.ai_status.value,
        snapshot_path=event.snapshot_path,
        occurred_at=event.occurred_at,
        note=event.note,
        verified_intruder=event.verified_intruder,
        protocols_activated=event.protocols_activated,
        distance_meters=event.distance_meters,
        dwell_time_seconds=event.dwell_time_seconds,
        expires_at=event.expires_at,
        snapshot_base64=snapshot_base64,
    )


@router.post("/{user_id}/properties/{pid}/events/{eid}/verify")
def verify_event(
    user_id: int,
    pid: int,
    eid: int,
    payload: VerifyEventRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    ensure_user_scope(user_id, current_user)
    _get_property_for_user(db, user_id, pid)
    event = db.scalar(select(Event).where(and_(Event.id == eid, Event.property_id == pid)))
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if event.ai_status != EventStatus.HUMAN_REVIEW:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only human_review events can be verified")

    event.verified_intruder = payload.confirmed_intruder
    event.note = "Owner confirmed intruder" if payload.confirmed_intruder else "Owner dismissed event"
    db.commit()

    if payload.confirmed_intruder:
        background_tasks.add_task(run_owner_intruder_confirmation_task, event.id, pid)

    return {"message": "Event verification recorded"}
