from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_db_session, require_webhook_security
from app.models import Event, Person, Property
from app.schemas.schemas import IntruderWebhookRequest
from app.services.decision_service import map_similarity_to_status
from app.services.file_service import save_event_snapshot_from_base64
from app.services.notification_service import run_owner_notification_flow_task

router = APIRouter(prefix="/webhooks", tags=["webhook"])


@router.post("/intruder")
async def intruder_webhook(
    payload: IntruderWebhookRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_webhook_security),
    db: Session = Depends(get_db_session),
) -> dict[str, str | int]:
    property_obj = db.get(Property, payload.property_id)
    if not property_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    if payload.person_id is not None:
        linked_person = db.scalar(
            select(Person).where(Person.id == payload.person_id, Person.property_id == payload.property_id)
        )
        if not linked_person:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="person_id does not belong to property")
        if not linked_person.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="person_id is not active")

    event_status = map_similarity_to_status(payload.similarity_score)
    snapshot_path = None
    if payload.snapshot_base64:
        snapshot_path = await save_event_snapshot_from_base64(payload.property_id, payload.snapshot_base64)

    event = Event(
        property_id=payload.property_id,
        person_id=payload.person_id,
        similarity_score=payload.similarity_score,
        status=event_status,
        snapshot_path=snapshot_path,
        occurred_at=payload.occurred_at or datetime.utcnow(),
        note=payload.note,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    owner_email = property_obj.user.email if property_obj.user else None
    background_tasks.add_task(run_owner_notification_flow_task, event.id, property_obj.id, owner_email)

    if event_status.value == "verified_intruder":
        # Demo escalation placeholder for high-confidence intruder detection.
        event.note = (event.note + " | demo_alarm=true") if event.note else "demo_alarm=true"
        db.commit()

    return {"event_id": event.id, "status": event.status.value}
