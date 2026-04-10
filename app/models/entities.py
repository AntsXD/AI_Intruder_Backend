from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EventStatus(str, Enum):
    AUTHORIZED = "authorized"
    INTRUDER = "intruder"
    HUMAN_REVIEW = "human_review"


class NotificationChannel(str, Enum):
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
    TELEGRAM = "telegram"


class NotificationStatus(str, Enum):
    SENT = "sent"
    FAILED = "failed"


class StreamType(str, Enum):
    HTTP_PROXY = "http_proxy"
    EXTERNAL_HLS = "external_hls"
    EXTERNAL_WEBRTC = "external_webrtc"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True,nullable=False)
    full_name: Mapped[str] = mapped_column(String(255))
    phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    properties: Mapped[list[Property]] = relationship("Property", back_populates="user", cascade="all, delete-orphan")
    consents: Mapped[list[UserConsent]] = relationship("UserConsent", back_populates="user", cascade="save-update, merge", passive_deletes=True)
    device_tokens: Mapped[list[UserDeviceToken]] = relationship(
        "UserDeviceToken", back_populates="user", cascade="all, delete-orphan"
    )


class UserDeviceToken(Base):
    __tablename__ = "user_device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="device_tokens")


class UserConsent(Base):
    __tablename__ = "user_consents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    consent_type: Mapped[str] = mapped_column(String(100), default="privacy_policy")
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User | None] = relationship("User", back_populates="consents")


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="properties")
    persons: Mapped[list[Person]] = relationship("Person", back_populates="property", cascade="all, delete-orphan")
    events: Mapped[list[Event]] = relationship("Event", back_populates="property", cascade="all, delete-orphan")
    protocol_assignments: Mapped[list[ProtocolAssignment]] = relationship(
        "ProtocolAssignment", back_populates="property", cascade="all, delete-orphan"
    )
    camera_stream: Mapped[CameraStream | None] = relationship(
        "CameraStream", back_populates="property", cascade="all, delete-orphan", uselist=False
    )


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    property: Mapped[Property] = relationship("Property", back_populates="persons")
    photos: Mapped[list[PersonPhoto]] = relationship("PersonPhoto", back_populates="person", cascade="all, delete-orphan")


class PersonPhoto(Base):
    __tablename__ = "person_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    is_display: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped[Person] = relationship("Person", back_populates="photos")


class Protocol(Base):
    __tablename__ = "protocols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    assignments: Mapped[list[ProtocolAssignment]] = relationship(
        "ProtocolAssignment", back_populates="protocol", cascade="all, delete-orphan"
    )


class ProtocolAssignment(Base):
    __tablename__ = "protocol_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    protocol_id: Mapped[int] = mapped_column(ForeignKey("protocols.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    property: Mapped[Property] = relationship("Property", back_populates="protocol_assignments")
    protocol: Mapped[Protocol] = relationship("Protocol", back_populates="assignments")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    ai_status: Mapped[EventStatus] = mapped_column(SqlEnum(EventStatus), index=True)
    snapshot_path: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_intruder: Mapped[bool] = mapped_column(Boolean, default=False)
    protocols_activated: Mapped[bool] = mapped_column(Boolean, default=False)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    dwell_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow() + timedelta(hours=72))

    property: Mapped[Property] = relationship("Property", back_populates="events")
    notifications: Mapped[list[NotificationLog]] = relationship(
        "NotificationLog", back_populates="event", cascade="all, delete-orphan"
    )


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    channel: Mapped[NotificationChannel] = mapped_column(SqlEnum(NotificationChannel), index=True)
    status: Mapped[NotificationStatus] = mapped_column(SqlEnum(NotificationStatus), index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped[Event] = relationship("Event", back_populates="notifications")


class CameraStream(Base):
    __tablename__ = "camera_streams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), unique=True, index=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    stream_type: Mapped[StreamType] = mapped_column(SqlEnum(StreamType), default=StreamType.HTTP_PROXY)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    property: Mapped[Property] = relationship("Property", back_populates="camera_stream")
