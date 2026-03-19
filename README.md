# AI Intruder Detection Backend (FastAPI)

This backend connects the AI detection service and mobile application for a demo intruder detection system.

## Scope
- Included: backend APIs, webhook ingestion, decision thresholds, authentication, SQLite persistence, image storage, notification orchestration.
- Excluded: frontend app and AI face recognition model.

## Key Decisions
- Authentication: Firebase ID token verification + backend-issued JWT access/refresh tokens.
- AI Integration: secure webhook receives events from AI service.
- Decision Matrix:
  - `similarity_score > 70`: `authorized`
  - `similarity_score < 50`: `intruder`
  - `50 <= similarity_score <= 70`: `human_review`
- Database: SQLite for demo.
- Notifications: push (FCM-ready stub), email (SMTP), SMS demo hook (optional), and demo alarm flag for high-confidence intruder.
- Camera feed forwarding: secure camera stream config + signed playback URLs + HTTP proxy forwarding endpoint.
- Image storage: filesystem under `storage/` with authenticated data access model at API level.

## Project Layout
```text
backend/
  app/
    main.py
    config.py
    database.py
    dependencies.py
    models/
      entities.py
    routers/
      auth.py
      users.py
      webhook.py
      streams.py
      health.py
    schemas/
      schemas.py
    services/
      firebase_service.py
      decision_service.py
      file_service.py
      notification_service.py
      stream_service.py
    utils/
      security.py
  storage/
  tests/
  requirements.txt
  .env.example
```

## Environment Setup
1. Create virtual environment and install dependencies.
2. Copy `.env.example` to `.env` and fill secrets.
3. Optional Firebase:
   - Set `FIREBASE_CREDENTIALS_PATH` to service account JSON path.
4. Optional SMTP:
   - Set `SMTP_ENABLED=true`, username, app password, sender.
5. Camera stream tokens:
   - `STREAM_TOKEN_MINUTES` (default: 10) - token expiry duration for camera feed access.

## Run
```bash
uvicorn app.main:app --reload 
```

API docs will be available at:
- `http://127.0.0.1:8000/docs`

## Demo Script (End-to-End)
Run the complete scripted flow (auth -> create resources -> upload photos -> activate person -> webhook -> verify event):

```bash
cd backend
python demo_flow.py
```

## Integration Tests
Run automated integration tests:

```bash
cd backend
pytest -q
```

## Auth Flow
1. Client sends Firebase ID token to:
   - `POST /api/v1/auth/verify-token`
2. Backend validates token and creates user if missing.
3. Backend returns JWT access token and refresh token.
4. Client uses `Authorization: Bearer <jwt>` for protected endpoints.

### Development Token Fallback
If Firebase is not configured, demo token format is accepted:
- `demo:<uid>:<email>:<name>`

## Core Endpoints
### Auth
- `POST /api/v1/auth/verify-token`
- `POST /api/v1/auth/refresh`

### User
- `GET /api/v1/users/{user_id}`
- `PUT /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`
- `POST /api/v1/users/{user_id}/consent`

### Properties
- `GET /api/v1/users/{user_id}/properties`
- `POST /api/v1/users/{user_id}/properties`
- `GET /api/v1/users/{user_id}/properties/{pid}`
- `PUT /api/v1/users/{user_id}/properties/{pid}`
- `DELETE /api/v1/users/{user_id}/properties/{pid}`

### Persons
- `GET /api/v1/users/{user_id}/properties/{pid}/persons`
- `POST /api/v1/users/{user_id}/properties/{pid}/persons`
- `GET /api/v1/users/{user_id}/properties/{pid}/persons/{person_id}`
- `PUT /api/v1/users/{user_id}/properties/{pid}/persons/{person_id}`
- `DELETE /api/v1/users/{user_id}/properties/{pid}/persons/{person_id}`
- `POST /api/v1/users/{user_id}/properties/{pid}/persons/{person_id}/photos`
- `GET /api/v1/users/{user_id}/properties/{pid}/persons/{person_id}/photos/{photo_id}`
- `DELETE /api/v1/users/{user_id}/properties/{pid}/persons/{person_id}/photos/{photo_id}`
- `POST /api/v1/users/{user_id}/properties/{pid}/persons/{person_id}/activate`

### Protocols
- `GET /api/v1/users/{user_id}/properties/{pid}/protocols`
- `PUT /api/v1/users/{user_id}/properties/{pid}/protocols`

### Events
- `GET /api/v1/users/{user_id}/properties/{pid}/events` (supports query params: `limit`, `offset`, `status_filter`)
- `GET /api/v1/users/{user_id}/properties/{pid}/events/{eid}`
- `POST /api/v1/users/{user_id}/properties/{pid}/events/{eid}/verify`

### Webhook
- `POST /api/v1/webhooks/intruder`
- Header: `X-Webhook-Api-Key: <WEBHOOK_API_KEY>`
- Optional signed-mode headers when `WEBHOOK_SIGNING_SECRET` is configured:
  - `X-Webhook-Timestamp: <unix-seconds>`
  - `X-Webhook-Signature: sha256=<hmac_of_timestamp_dot_raw_body>`

### Camera Feed
- `PUT /api/v1/users/{user_id}/properties/{pid}/camera-feed`
- `GET /api/v1/users/{user_id}/properties/{pid}/camera-feed`
- `GET /api/v1/streams/{stream_id}/play?token=...`
  - `http_proxy` mode streams bytes through backend to frontend.
  - `external_hls`/`external_webrtc` modes issue secure signed redirect links.

### Health
- `GET /api/v1/health`

## Webhook Payload Example
```json
{
  "property_id": 1,
  "similarity_score": 47.3,
  "person_id": null,
  "snapshot_base64": "<base64-jpeg>",
  "note": "Unknown face detected at front door"
}
```

## Response Examples

### Photo Upload Response
```json
{
  "photo_id": 1,
  "file_path": "storage/property_1/person_2/photo_1.jpg"
}
```

## Database Entities
- `users`
- `user_consents`
- `properties`
- `persons`
- `person_photos`
- `protocols`
- `protocol_assignments` (intermediary optimization)
- `events`
- `notification_logs`
- `camera_streams`

## Presentation Demo Script
1. Authenticate with a demo Firebase token.
2. Create property and allowed person.
3. Upload 3-5 person photos.
4. Activate person for recognition.
4. Trigger webhook with score:
   - `45` for intruder branch
   - `60` for human review branch
   - `85` for authorized branch
5. Fetch events and verify a human-review event from owner endpoint.
6. Show notification logs and event notes.
7. Configure camera feed and test signed playback URL in browser/app.

## Current Status
- Completed: core API architecture and required routes.
- Completed: threshold decision logic and webhook API key + optional HMAC replay protection.
- Completed: notification channel abstraction with email and push stub.
- Completed: secure camera feed forwarding endpoints.
- Completed: stronger test coverage, production migration path,
- In progress: real FCM provider integration, working on camera feed system
