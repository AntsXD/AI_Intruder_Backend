import logging
import smtplib
import json
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models.entities import Event, EventStatus, NotificationChannel, NotificationLog, NotificationStatus, Person, Property, UserDeviceToken
from app.services.firebase_service import send_fcm_notification


def log_notification(db, event: Event, channel: NotificationChannel, status: NotificationStatus, detail: str | None = None) -> None:
    row = NotificationLog(event_id=event.id, channel=channel, status=status, detail=detail)
    db.add(row)
    db.commit()


def _build_push_content(event: Event, property_name: str, person_name: str | None) -> tuple[str, str, str]:
    if event.ai_status == EventStatus.AUTHORIZED:
        label = person_name or "Known person"
        return (
            f"Known Person Detected - {property_name}",
            f"{label} recognized at {property_name} (event {event.id}, score={event.similarity_score:.1f}).",
            "known_person",
        )

    if event.ai_status == EventStatus.HUMAN_REVIEW:
        return (
            f"Unknown Person Detected - {property_name}",
            f"Unknown visitor needs review at {property_name} (event {event.id}, score={event.similarity_score:.1f}).",
            "unknown_person",
        )

    return (
        f"Intruder Alert - {property_name}",
        f"Intruder detected at {property_name} (event {event.id}, score={event.similarity_score:.1f}).",
        "intruder",
    )


def _build_email_content(event: Event, property_name: str, person_name: str | None) -> tuple[str, str]:
    if event.ai_status == EventStatus.AUTHORIZED:
        label = person_name or "Known person"
        subject = f"Known Person Update - {property_name}"
        body = (
            f"Event ID: {event.id}\n"
            f"Property: {property_name}\n"
            f"Status: known_person\n"
            f"Person: {label}\n"
            f"Score: {event.similarity_score:.1f}\n"
        )
        return subject, body

    if event.ai_status == EventStatus.HUMAN_REVIEW:
        subject = f"Unknown Person Review Needed - {property_name}"
        body = (
            f"Event ID: {event.id}\n"
            f"Property: {property_name}\n"
            f"Status: unknown_person\n"
            f"Score: {event.similarity_score:.1f}\n"
            "Action: Please review this event in the app.\n"
        )
        return subject, body

    subject = f"Intruder Alert - {property_name}"
    body = (
        f"Event ID: {event.id}\n"
        f"Property: {property_name}\n"
        "Status: intruder\n"
        f"Score: {event.similarity_score:.1f}\n"
        "Action: Please review immediately in the app.\n"
    )
    return subject, body


def send_push_notification(db, event: Event, property_obj: Property, person_name: str | None = None) -> None:
    if not settings.fcm_enabled:
        logger.debug("FCM disabled — skipping push for event %s", event.id)
        return

    owner_id = property_obj.user_id
    token_rows = db.scalars(select(UserDeviceToken).where(UserDeviceToken.user_id == owner_id)).all()
    if not token_rows:
        logger.warning("No FCM device tokens registered for user %s", owner_id)
        log_notification(db, event, NotificationChannel.PUSH, NotificationStatus.FAILED, "No FCM device tokens registered")
        return

    logger.info("Sending FCM notification to %d device(s) for event %s", len(token_rows), event.id)

    resolved_person_name = person_name
    if not resolved_person_name and event.person_id:
        person = db.get(Person, event.person_id)
        if person:
            resolved_person_name = person.name

    title, body, alert_level = _build_push_content(event, property_obj.name, resolved_person_name)
    data = {
        "event_id": str(event.id),
        "property_id": str(property_obj.id),
        "status": event.ai_status.value,
        "alert_level": alert_level,
        "similarity_score": f"{event.similarity_score:.1f}",
    }
    if resolved_person_name:
        data["person_name"] = resolved_person_name

    success = 0
    failed = 0
    for row in token_rows:
        try:
            send_fcm_notification(token=row.token, title=title, body=body, data=data)
            success += 1
        except Exception as exc:
            if "NotRegistered" in str(exc) or "InvalidRegistration" in str(exc):
                logger.warning("Removing stale FCM token for user %s: %s", owner_id, exc)
                db.delete(row)
                db.commit()
            else:
                logger.warning("FCM send failed for token %r: %s", row.token, exc)
            failed += 1

    if success > 0:
        logger.info("FCM sent to %d device(s)", success)
        log_notification(db, event, NotificationChannel.PUSH, NotificationStatus.SENT, f"FCM sent to {success} device(s)")
    if failed > 0:
        logger.warning("FCM failed for %d device(s)", failed)
        log_notification(db, event, NotificationChannel.PUSH, NotificationStatus.FAILED, f"FCM failed for {failed} device(s)")


def send_email_alert(db, event: Event, property_obj: Property, recipient: str | None, person_name: str | None = None) -> None:
    if not settings.smtp_enabled or not recipient:
        return

    subject, body = _build_email_content(event, property_obj.name, person_name)

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


def send_telegram_alert(db, event: Event, property_obj: Property) -> None:
    if not settings.telegram_enabled:
        return
    if not settings.telegram_bot_token or not settings.telegram_fake_chat_id:
        logger.warning("Telegram not configured — missing bot token or chat id")
        return

    text = (
        f"Intruder Confirmed\n"
        f"Property: {property_obj.name}\n"
        f"Score: {event.similarity_score:.1f}\n"
        f"Event ID: {event.id}"
    )
    url = (
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        f"?chat_id={settings.telegram_fake_chat_id}"
        f"&text={urllib.parse.quote(text)}"
    )

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                log_notification(db, event, NotificationChannel.TELEGRAM, NotificationStatus.SENT, f"Telegram sent to {settings.telegram_fake_chat_id}")
                logger.info("Telegram alert sent for event %s", event.id)
            else:
                log_notification(db, event, NotificationChannel.TELEGRAM, NotificationStatus.FAILED, f"HTTP {resp.status}")
    except urllib.error.URLError as exc:
        log_notification(db, event, NotificationChannel.TELEGRAM, NotificationStatus.FAILED, str(exc))
        logger.warning("Telegram alert failed for event %s: %s", event.id, exc)


def run_owner_notification_flow(
    db,
    event: Event,
    property_obj: Property,
    owner_email: str | None,
    person_name: str | None = None,
) -> None:
    send_push_notification(db, event, property_obj, person_name)
    send_email_alert(db, event, property_obj, owner_email, person_name)


def run_owner_notification_flow_task(
    event_id: int,
    property_id: int,
    owner_email: str | None,
    person_name: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        property_obj = db.get(Property, property_id)
        if not event or not property_obj:
            return
        run_owner_notification_flow(db, event, property_obj, owner_email, person_name)
    finally:
        db.close()


def run_owner_intruder_confirmation_task(event_id: int, property_id: int) -> None:
    db = SessionLocal()
    try:
        event = db.get(Event, event_id)
        property_obj = db.get(Property, property_id)
        if not event or not property_obj:
            return
        if event.ai_status.value != "human_review" or not event.verified_intruder:
            return
        send_telegram_alert(db, event, property_obj)
    finally:
        db.close()
