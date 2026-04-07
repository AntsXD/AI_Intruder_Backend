# Frontend Integration Flow

Use this flow with Firebase authentication on the mobile app.

## 1) Sign up or login with Firebase

Use Firebase SDK on the frontend (`createUserWithEmailAndPassword` or `signInWithEmailAndPassword`).

Then obtain Firebase ID token:

```ts
const firebaseToken = await firebaseUser.getIdToken();
```

## 2) Exchange Firebase token for backend JWTs

`POST /api/v1/auth/verify-token`

Request body:

```json
{
  "firebase_token": "<firebase-id-token>"
}
```

Response body:

```json
{
  "user_id": 1,
  "access_token": "<backend-access-token>",
  "refresh_token": "<backend-refresh-token>",
  "token_type": "bearer"
}
```

Use `user_id` for user-scoped endpoints and `access_token` for all protected backend requests.

## 3) Fetch user profile

`GET /api/v1/users/{user_id}`

Header:

```text
Authorization: Bearer <backend-access-token>
```

## 4) Save user details (name, phone)

`PUT /api/v1/users/{user_id}`

Request body:

```json
{
  "full_name": "John Doe",
  "phone_number": "+35612345678"
}
```

## 5) Optional onboarding calls

- Record consent: `POST /api/v1/users/{user_id}/consent`
- Create property: `POST /api/v1/users/{user_id}/properties`
- Create recognized person profile: `POST /api/v1/users/{user_id}/properties/{pid}/persons`

## 6) Refresh backend token when expired

`POST /api/v1/auth/refresh`

Request body:

```json
{
  "refresh_token": "<backend-refresh-token>"
}
```

Store the new `access_token` and `refresh_token` returned by this endpoint.

## Notes

- Frontend should not call backend `signup` or `login` endpoints (they do not exist).
- Auth source of truth is Firebase for identity, and backend JWT for API authorization.
