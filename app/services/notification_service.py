import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings
from app.database import SessionLocal
from app.models.entities import Event, NotificationChannel, NotificationLog, NotificationStatus, Property


def log_notification(db, event: Event, channel: NotificationChannel, status: NotificationStatus, detail: str | None = None) -> None:
    row = NotificationLog(event_id=event.id, channel=channel, status=status, detail=detail)
    db.add(row)
    db.commit()


def send_push_notification_stub(db, event: Event, property_obj: Property) -> None:
    detail = f"FCM demo: Event {event.id} status={event.ai_status.value} at property={property_obj.name}"
    log_notification(db, event, NotificationChannel.PUSH, NotificationStatus.SENT, detail)


def send_sms_demo(db, event: Event, property_obj: Property) -> None:
    if not settings.sms_enabled:
        return
    detail = f"SMS demo alert for property {property_obj.name}, event {event.id}"
    log_notification(db, event, NotificationChannel.SMS, NotificationStatus.SENT, detail)


def send_email_alert(db, event: Event, property_obj: Property, recipient: str | None) -> None:
    if not settings.smtp_enabled or not recipient:
        return

    subject = f"Intruder Alert - {property_obj.name}"
    body = (
        f"Event ID: {event.id}\n"
        f"Property: {property_obj.name}\n"
        f"Score: {event.similarity_score}\n"
        f"Status: {event.ai_status.value}\n"
    )

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from or settings.smtp_username
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_app_password)
            server.send_message(msg)
        log_notification(db, event, NotificationChannel.EMAIL, NotificationStatus.SENT, "Email sent")
    except Exception as exc:
        log_notification(db, event, NotificationChannel.EMAIL, NotificationStatus.FAILED, str(exc))


def run_owner_notification_flow(db, event: Event, property_obj: Property, owner_email: str | None) -> None:
    send_push_notification_stub(db, event, property_obj)
    if event.ai_status.value in {"intruder", "human_review"}:
        send_email_alert(db, event, property_obj, owner_email)
        send_sms_demo(db, event, property_obj)


def run_owner_notification_flow_task(event_id: int, property_id: int, owner_email: str | None) -> None:
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        property_obj = db.get(Property, property_id)
        if not event or not property_obj:
            return
        run_owner_notification_flow(db, event, property_obj, owner_email)
    finally:
        db.close()


def run_owner_intruder_confirmation_task(event_id: int, property_id: int) -> None:
    """
    Triggered when the owner confirms an intruder on a human_review event.

    For demo scope this reuses the existing notification channels and logs a clear
    audit trail entry, so the app can show that confirmation actions happened.
    """
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        property_obj = db.get(Property, property_id)
        if not event or not property_obj:
            return

        owner_email = property_obj.user.email if property_obj.user else None
        log_notification(
            db,
            event,
            NotificationChannel.PUSH,
            NotificationStatus.SENT,
            f"Owner confirmed intruder for event {event.id} at property={property_obj.name}",
        )
        send_email_alert(db, event, property_obj, owner_email)
        send_sms_demo(db, event, property_obj)
    finally:
        db.close()
