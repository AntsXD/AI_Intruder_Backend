def test_verify_and_refresh_token(client, make_auth_headers) -> None:
    verify = client.post(
        "/api/v1/auth/verify-token",
        json={"firebase_token": "demo:test-auth:test@example.com:Test Auth"},
    )
    assert verify.status_code == 200

    body = verify.json()
    assert "access_token" in body
    assert "refresh_token" in body

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refresh.status_code == 200
    refreshed = refresh.json()
    assert "access_token" in refreshed
    assert "refresh_token" in refreshed

    user_id, headers = make_auth_headers(uid="auth-scope")
    profile = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert profile.status_code == 200
