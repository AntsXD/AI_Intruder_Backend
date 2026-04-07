# API Client

This folder contains a small TypeScript client for the FastAPI backend.

## Usage

```ts
import { ApiClient } from "./client";

const api = new ApiClient({ baseUrl: "http://127.0.0.1:8000" });

// 1) Frontend authenticates with Firebase SDK and gets an ID token.
// const firebaseToken = await firebaseUser.getIdToken();
const firebaseToken = "<firebase-id-token>";

// 2) Exchange Firebase token for backend access/refresh tokens.
const auth = await api.verifyFirebaseToken({ firebase_token: firebaseToken });
api.setAccessToken(auth.access_token);

// 3) Use backend JWT for protected API calls.
const profile = await api.getUser(1);
```

## Authentication notes

- Signup/login should be done on the frontend via Firebase SDK.
- The backend auth flow starts at `verifyFirebaseToken()`.
- Use `refreshToken()` when backend access token expires.