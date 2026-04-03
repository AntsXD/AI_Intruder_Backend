def test_verify_and_refresh_token(client, make_auth_headers, real_firebase_token) -> None:
    
    # Part 1 — Exchange real Firebase token
    verify = client.post(
        "/api/v1/auth/verify-token",
        json={"firebase_token": real_firebase_token},
    )
    assert verify.status_code == 200, f"verify-token failed: {verify.json()}"

    body = verify.json()
    assert "access_token"  in body
    assert "refresh_token" in body

    # Part 2 — Refresh
    refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]}
    )
    assert refresh.status_code == 200, f"refresh failed: {refresh.json()}"

    refreshed = refresh.json()
    assert "access_token"  in refreshed
    assert "refresh_token" in refreshed

    # Part 3 — Protected route
    user_id, headers = make_auth_headers()   # ← no uid argument anymore
    profile = client.get(f"/api/v1/users/{user_id}", headers=headers)
    assert profile.status_code == 200, f"profile failed: {profile.json()}"