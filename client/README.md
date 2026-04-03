# API Client

This folder contains a small TypeScript client for the FastAPI backend.

## Usage

```ts
import { ApiClient } from "./client";

const api = new ApiClient({ baseUrl: "http://127.0.0.1:8000" });

const auth = await api.verifyFirebaseToken({ firebase_token: "demo:user-1:user@example.com:Demo User" });
api.setAccessToken(auth.access_token);

const profile = await api.getUser(1);
```

## Auth stubs

`signUp()` and `login()` are intentionally stubbed until matching backend endpoints are added.