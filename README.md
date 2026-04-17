# AI Intruder Detection Backend (FastAPI)

Backend service for an intruder-detection demo system. It exposes authenticated owner APIs, ingests AI webhook events, stores snapshots and metadata, and manages camera feed playback links.

## What This Service Does
- Verifies Firebase ID tokens and issues backend JWT access/refresh tokens.
- Manages users, properties, persons, person photos, event history, and protocols.
- Accepts secured webhook events from an AI detection service.
- Classifies webhook events using threshold logic.
- Supports owner verification for human-review events.
- Supports camera feed configuration with signed playback URLs.
- Stores files locally under the configured storage directory.

## Tech Stack
- FastAPI
- SQLAlchemy
- SQLite (default)
- Pydantic v2
- Firebase Admin SDK (token verification and optional FCM sending)

## Project Structure
## Key Decisions
- Authentication: Firebase ID token verification + backend-issued JWT access/refresh tokens.
- AI Integration: secure webhook receives events from AI service.
- Decision Matrix:
  - `similarity_score > 70`: `authorized`
  - `similarity_score < 50`: `intruder`
  - `50 <= similarity_score <= 70`: `human_review`
- Database: SQLite for demo.
- Notifications: push (FCM-ready stub), email (SMTP), and Telegram alerts sent after owner confirms a human-review event is an intruder.
- Camera feed forwarding: secure camera stream config + signed playback URLs + HTTP proxy forwarding endpoint.
- Image storage: filesystem under `storage/` with authenticated data access model at API level.

## Project Layout
```text
app/
  main.py
  config.py
  database.py
  dependencies.py
  init_db.py
  models/
    entities.py
  routers/
    auth.py
    health.py
    streams.py
    users.py
    webhook.py
  schemas/
    schemas.py
  services/
    decision_service.py
    file_service.py
    firebase_service.py
    notification_service.py
    stream_service.py
  utils/
    security.py
storage/
tests/
requirements.txt
.env.example
demo_flow.py
```

## Quick Start
1. Create and activate a virtual environment.

Windows PowerShell:
```powershell
python -m venv backend
.\backend\Scripts\Activate.ps1
```

macOS/Linux:
```bash
python -m venv backend
source backend/bin/activate
```

2. Install dependencies.
```bash
pip install -r requirements.txt
```

3. Copy environment template and configure values.
```bash
copy .env.example .env
```

4. Start the API.
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Docs:
- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/redoc

## Environment Variables
Configured in .env. Important values:

- APP_NAME
- ENV
- API_PREFIX
- JWT_SECRET_KEY
- JWT_ALGORITHM
- JWT_ACCESS_TOKEN_MINUTES
- JWT_REFRESH_TOKEN_DAYS
- DATABASE_URL
- STORAGE_ROOT
- CORS_ORIGINS
- AUTO_CREATE_TABLES

Webhook security:
- WEBHOOK_API_KEY
- WEBHOOK_SIGNING_SECRET (optional, enables HMAC signature validation)
- WEBHOOK_SIGNATURE_TOLERANCE_SECONDS

Firebase:
- FIREBASE_CREDENTIALS_PATH (required for verify-token endpoint)
- FCM_ENABLED

Notifications:
- SMTP_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_APP_PASSWORD, SMTP_FROM
- TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_FAKE_CHAT_ID

AI registration on person activation:
- AI_SERVICE_URL
- AI_SERVICE_API_KEY

Camera feed token lifetime:
- STREAM_TOKEN_MINUTES

## Authentication Model
1. Client sends Firebase ID token to POST /api/v1/auth/verify-token.
2. Backend validates the token via Firebase Admin.
3. If user does not exist, account is created when consent_accepted is true.
4. Backend returns access_token and refresh_token.
5. Protected routes require Authorization: Bearer <access_token>.

Notes:
- There is no demo token fallback in the current implementation.
- If Firebase is not configured, verify-token returns HTTP 503.

## Decision Thresholds
- similarity_score greater than 70: authorized
- similarity_score less than 50: intruder
- similarity_score from 50 to 70 inclusive: human_review

## API Endpoints
Base prefix: /api/v1

Auth:
- POST /auth/verify-token
- POST /auth/refresh
- POST /auth/revoke-consent

Health:
- GET /health

Users:
- GET /users/{user_id}
- PUT /users/{user_id}
- DELETE /users/{user_id}

Device tokens (FCM):
- POST /users/{user_id}/devices/fcm-token
- DELETE /users/{user_id}/devices/fcm-token

Properties:
- GET /users/{user_id}/properties
- POST /users/{user_id}/properties
- GET /users/{user_id}/properties/{pid}
- PUT /users/{user_id}/properties/{pid}
- DELETE /users/{user_id}/properties/{pid}

Persons:
- GET /users/{user_id}/properties/{pid}/persons
- POST /users/{user_id}/properties/{pid}/persons
- GET /users/{user_id}/properties/{pid}/persons/{person_id}
- PUT /users/{user_id}/properties/{pid}/persons/{person_id}
- DELETE /users/{user_id}/properties/{pid}/persons/{person_id}
- POST /users/{user_id}/properties/{pid}/persons/{person_id}/activate

Person photos:
- POST /users/{user_id}/properties/{pid}/persons/{person_id}/photos
- GET /users/{user_id}/properties/{pid}/persons/{person_id}/photos/{photo_id}
- DELETE /users/{user_id}/properties/{pid}/persons/{person_id}/photos/{photo_id}

Protocols:
- GET /users/{user_id}/properties/{pid}/protocols
- PUT /users/{user_id}/properties/{pid}/protocols

Events:
- GET /users/{user_id}/properties/{pid}/events
- GET /users/{user_id}/properties/{pid}/events/{eid}
- POST /users/{user_id}/properties/{pid}/events/{eid}/verify

Camera feed:
- PUT /users/{user_id}/properties/{pid}/camera-feed
- GET /users/{user_id}/properties/{pid}/camera-feed
- GET /streams/{stream_id}/play?token=...

Webhook:
- POST /webhooks/intruder
  - Required header: X-Webhook-Api-Key
  - Optional signed mode headers when WEBHOOK_SIGNING_SECRET is set:
    - X-Webhook-Timestamp
    - X-Webhook-Signature (format: sha256=<digest>)

## Behavioral Rules Worth Knowing
- Person activation requires exactly 3 photos.
- Each person photo type must be unique (face, left_profile, right_profile).
- Event verification is allowed only for human_review events.
- Camera playback token is scoped to user and stream.
- For external_hls and external_webrtc stream types, playback endpoint redirects.
- For http_proxy stream type, playback endpoint proxies bytes through backend.

## Webhook Payload Example
```json
{
  "property_id": 1,
  "similarity_score": 47.3,
  "person_id": null,
  "person_name": "Unknown",
  "snapshot_base64": "<base64-jpeg>",
  "note": "Unknown face detected at front door"
}
```

## Testing
Run tests:

```bash
pytest -q
```

## Demo Flow Script
An optional script exists for end-to-end demo flow:

```bash
python demo_flow.py
```

The script still depends on a valid environment setup, including authentication prerequisites.
