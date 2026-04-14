export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface ClientOptions {
  baseUrl?: string;
  accessToken?: string;
  fetchImpl?: typeof fetch;
}

export interface TokenResponse {
  user_id: number;
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface VerifyTokenRequest {
  firebase_token: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface ConsentRequest {
  consent_type?: string;
  accepted?: boolean;
}

export interface UserUpdateRequest {
  full_name?: string;
  phone_number?: string;
}

export interface DeviceTokenUpsertRequest {
  token: string;
  device_name?: string | null;
}

export interface DeviceTokenDeleteRequest {
  token: string;
}

export interface PropertyCreateRequest {
  name: string;
  address?: string | null;
}

export interface PropertyUpdateRequest {
  name?: string | null;
  address?: string | null;
}

export interface PersonCreateRequest {
  name: string;
}

export interface PersonUpdateRequest {
  name?: string | null;
}

export interface VerifyEventRequest {
  confirmed_intruder: boolean;
}

export interface CameraFeedUpsertRequest {
  source_url: string;
  stream_type?: "http_proxy" | "external_hls" | "external_webrtc";
  is_enabled?: boolean;
}

export interface UserOut {
  id: number;
  firebase_uid: string;
  email: string;
  full_name: string;
  phone_number?: string | null;
  created_at: string;
}

export interface PropertyOut {
  id: number;
  user_id: number;
  name: string;
  address?: string | null;
  created_at: string;
}

export interface PersonOut {
  id: number;
  property_id: number;
  name: string;
  is_active: boolean;
  created_at: string;
}

export interface PersonActivationResponse {
  person_id: number;
  is_active: boolean;
  photo_count: number;
  has_display_photo: boolean;
  message: string;
}

export interface EventOut {
  id: number;
  property_id: number;
  person_id?: number | null;
  similarity_score: number;
  ai_status: string;
  snapshot_path: string;
  occurred_at: string;
  note?: string | null;
  verified_intruder: boolean;
  protocols_activated: boolean;
  distance_meters?: number | null;
  dwell_time_seconds?: number | null;
  expires_at: string;
}

export interface EventDetailOut extends EventOut {
  snapshot_base64: string;
  snapshot_mime_type: string;
}

export interface CameraFeedOut {
  property_id: number;
  source_url: string;
  stream_type: string;
  is_enabled: boolean;
  playback_url: string;
}

export interface MessageResponse {
  message: string;
}

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/$/, "");
}

function buildQueryString(params?: Record<string, string | number | boolean | undefined | null>): string {
  if (!params) {
    return "";
  }

  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) {
      continue;
    }
    searchParams.set(key, String(value));
  }

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private accessToken?: string;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = normalizeBaseUrl(options.baseUrl ?? "http://127.0.0.1:8000");
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.accessToken = options.accessToken;
  }

  setAccessToken(accessToken?: string): void {
    this.accessToken = accessToken;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers);

    if (this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }

    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    const contentType = response.headers.get("content-type") ?? "";
    const isJson = contentType.includes("application/json");

    if (!response.ok) {
      const payload = isJson ? await response.json().catch(() => null) : await response.text().catch(() => "");
      const message =
        typeof payload === "object" && payload !== null && "detail" in payload
          ? String((payload as { detail: unknown }).detail)
          : `Request failed with status ${response.status}`;
      throw new ApiError(response.status, message, payload);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    if (isJson) {
      return (await response.json()) as T;
    }

    return (await response.text()) as T;
  }

  private jsonRequest<T>(method: HttpMethod, path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method,
      headers: {
        "Content-Type": "application/json",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  getHealth(): Promise<{ status: string }> {
    return this.request<{ status: string }>("/api/v1/health");
  }

  verifyFirebaseToken(payload: VerifyTokenRequest): Promise<TokenResponse> {
    return this.jsonRequest<TokenResponse>("POST", "/api/v1/auth/verify-token", payload);
  }

  refreshToken(payload: RefreshTokenRequest): Promise<TokenResponse> {
    return this.jsonRequest<TokenResponse>("POST", "/api/v1/auth/refresh", payload);
  }

  getUser(userId: number): Promise<UserOut> {
    return this.request<UserOut>(`/api/v1/users/${userId}`);
  }

  updateUser(userId: number, payload: UserUpdateRequest): Promise<UserOut> {
    return this.jsonRequest<UserOut>("PUT", `/api/v1/users/${userId}`, payload);
  }

  upsertFcmToken(userId: number, payload: DeviceTokenUpsertRequest): Promise<MessageResponse> {
    return this.jsonRequest<MessageResponse>("POST", `/api/v1/users/${userId}/devices/fcm-token`, payload);
  }

  deleteFcmToken(userId: number, payload: DeviceTokenDeleteRequest): Promise<MessageResponse> {
    return this.jsonRequest<MessageResponse>("DELETE", `/api/v1/users/${userId}/devices/fcm-token`, payload);
  }

  deleteUser(userId: number): Promise<MessageResponse> {
    return this.request<MessageResponse>(`/api/v1/users/${userId}`, { method: "DELETE" });
  }

  addConsent(userId: number, payload: ConsentRequest): Promise<MessageResponse> {
    return this.jsonRequest<MessageResponse>("POST", `/api/v1/users/${userId}/consent`, payload);
  }

  listProperties(userId: number): Promise<PropertyOut[]> {
    return this.request<PropertyOut[]>(`/api/v1/users/${userId}/properties`);
  }

  createProperty(userId: number, payload: PropertyCreateRequest): Promise<PropertyOut> {
    return this.jsonRequest<PropertyOut>("POST", `/api/v1/users/${userId}/properties`, payload);
  }

  getProperty(userId: number, propertyId: number): Promise<PropertyOut> {
    return this.request<PropertyOut>(`/api/v1/users/${userId}/properties/${propertyId}`);
  }

  updateProperty(userId: number, propertyId: number, payload: PropertyUpdateRequest): Promise<PropertyOut> {
    return this.jsonRequest<PropertyOut>("PUT", `/api/v1/users/${userId}/properties/${propertyId}`, payload);
  }

  deleteProperty(userId: number, propertyId: number): Promise<MessageResponse> {
    return this.request<MessageResponse>(`/api/v1/users/${userId}/properties/${propertyId}`, {
      method: "DELETE",
    });
  }

  listPersons(userId: number, propertyId: number): Promise<PersonOut[]> {
    return this.request<PersonOut[]>(`/api/v1/users/${userId}/properties/${propertyId}/persons`);
  }

  createPerson(userId: number, propertyId: number, payload: PersonCreateRequest): Promise<PersonOut> {
    return this.jsonRequest<PersonOut>("POST", `/api/v1/users/${userId}/properties/${propertyId}/persons`, payload);
  }

  getPerson(userId: number, propertyId: number, personId: number): Promise<PersonOut> {
    return this.request<PersonOut>(`/api/v1/users/${userId}/properties/${propertyId}/persons/${personId}`);
  }

  updatePerson(userId: number, propertyId: number, personId: number, payload: PersonUpdateRequest): Promise<PersonOut> {
    return this.jsonRequest<PersonOut>("PUT", `/api/v1/users/${userId}/properties/${propertyId}/persons/${personId}`, payload);
  }

  deletePerson(userId: number, propertyId: number, personId: number): Promise<MessageResponse> {
    return this.request<MessageResponse>(`/api/v1/users/${userId}/properties/${propertyId}/persons/${personId}`, {
      method: "DELETE",
    });
  }

  activatePerson(userId: number, propertyId: number, personId: number): Promise<PersonActivationResponse> {
    return this.request<PersonActivationResponse>(`/api/v1/users/${userId}/properties/${propertyId}/persons/${personId}/activate`, {
      method: "POST",
    });
  }

  uploadPersonPhoto(
    userId: number,
    propertyId: number,
    personId: number,
    file: File | Blob,
    isDisplay = false,
  ): Promise<{ photo_id: number; file_path: string }> {
    const formData = new FormData();
    formData.set("file", file);

    return this.request<{ photo_id: number; file_path: string }>(
      `/api/v1/users/${userId}/properties/${propertyId}/persons/${personId}/photos${buildQueryString({ is_display: isDisplay })}`,
      {
        method: "POST",
        body: formData,
      },
    );
  }

  listEvents(userId: number, propertyId: number, params?: { limit?: number; offset?: number; status_filter?: string }): Promise<EventOut[]> {
    return this.request<EventOut[]>(
      `/api/v1/users/${userId}/properties/${propertyId}/events${buildQueryString(params)}`,
    );
  }

  getEvent(userId: number, propertyId: number, eventId: number): Promise<EventDetailOut> {
    return this.request<EventDetailOut>(`/api/v1/users/${userId}/properties/${propertyId}/events/${eventId}`);
  }

  verifyEvent(userId: number, propertyId: number, eventId: number, payload: VerifyEventRequest): Promise<MessageResponse> {
    return this.jsonRequest<MessageResponse>("POST", `/api/v1/users/${userId}/properties/${propertyId}/events/${eventId}/verify`, payload);
  }

  upsertCameraFeed(userId: number, propertyId: number, payload: CameraFeedUpsertRequest): Promise<CameraFeedOut> {
    return this.jsonRequest<CameraFeedOut>("PUT", `/api/v1/users/${userId}/properties/${propertyId}/camera-feed`, payload);
  }

  getCameraFeed(userId: number, propertyId: number): Promise<CameraFeedOut> {
    return this.request<CameraFeedOut>(`/api/v1/users/${userId}/properties/${propertyId}/camera-feed`);
  }

  buildStreamPlaybackUrl(streamId: number, token: string): string {
    return `${this.baseUrl}/api/v1/streams/${streamId}/play?token=${encodeURIComponent(token)}`;
  }
}

export const apiClient = new ApiClient();