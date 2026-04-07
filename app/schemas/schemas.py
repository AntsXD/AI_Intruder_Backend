from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    user_id: int
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class VerifyTokenRequest(BaseModel):
    firebase_token: str = Field(min_length=10)


class ConsentRequest(BaseModel):
    consent_type: str = "privacy_policy"
    accepted: bool = True


class UserCreate(BaseModel):
    firebase_uid: str
    email: EmailStr
    full_name: str
    phone_number: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None


class UserOut(BaseModel):
    id: int
    firebase_uid: str
    email: EmailStr
    full_name: str
    phone_number: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PropertyCreate(BaseModel):
    name: str
    address: str | None = None


class PropertyUpdate(BaseModel):
    name: str | None = None
    address: str | None = None


class PropertyOut(BaseModel):
    id: int
    user_id: int
    name: str
    address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PersonCreate(BaseModel):
    name: str


class PersonUpdate(BaseModel):
    name: str | None = None


class PersonOut(BaseModel):
    id: int
    property_id: int
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProtocolCreate(BaseModel):
    name: str
    description: str | None = None


class ProtocolUpdate(BaseModel):
    description: str | None = None


class ProtocolOut(BaseModel):
    id: int
    name: str
    description: str | None

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    property_id: int
    person_id: int | None
    similarity_score: float
    ai_status: str
    snapshot_path: str
    occurred_at: datetime
    note: str | None
    verified_intruder: bool
    protocols_activated: bool
    distance_meters: float | None
    dwell_time_seconds: float | None
    expires_at: datetime

    model_config = {"from_attributes": True}


class VerifyEventRequest(BaseModel):
    confirmed_intruder: bool


class IntruderWebhookRequest(BaseModel):
    property_id: int
    similarity_score: float = Field(ge=0, le=100)
    person_id: int | None = None
    snapshot_base64: str
    occurred_at: datetime | None = None
    note: str | None = None


class CameraFeedUpsertRequest(BaseModel):
    source_url: str
    stream_type: Literal["http_proxy", "external_hls", "external_webrtc"] = "http_proxy"
    is_enabled: bool = True


class CameraFeedOut(BaseModel):
    property_id: int
    source_url: str
    stream_type: str
    is_enabled: bool
    playback_url: str


class PersonActivationResponse(BaseModel):
    person_id: int
    is_active: bool
    photo_count: int
    has_display_photo: bool
    message: str


EventFilterStatus = Literal["authorized", "intruder", "human_review"]
