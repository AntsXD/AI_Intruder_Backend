def test_verify_only_human_review_events(client, webhook_headers, make_auth_headers) -> None:
    user_id, headers = make_auth_headers(uid="verify-user")

    prop = client.post(
        f"/api/v1/users/{user_id}/properties",
        json={"name": "Flat", "address": "A Street"},
        headers=headers,
    )
    assert prop.status_code == 200
    pid = prop.json()["id"]

    human_event = client.post(
        "/api/v1/webhooks/intruder",
        json={"property_id": pid, "similarity_score": 60.0, "note": "human review"},
        headers=webhook_headers,
    )
    assert human_event.status_code == 200
    human_eid = human_event.json()["event_id"]

    ok_verify = client.post(
        f"/api/v1/users/{user_id}/properties/{pid}/events/{human_eid}/verify",
        json={"confirmed_intruder": True},
        headers=headers,
    )
    assert ok_verify.status_code == 200

    intruder_event = client.post(
        "/api/v1/webhooks/intruder",
        json={"property_id": pid, "similarity_score": 40.0, "note": "intruder"},
        headers=webhook_headers,
    )
    assert intruder_event.status_code == 200
    intruder_eid = intruder_event.json()["event_id"]

    bad_verify = client.post(
        f"/api/v1/users/{user_id}/properties/{pid}/events/{intruder_eid}/verify",
        json={"confirmed_intruder": True},
        headers=headers,
    )
    assert bad_verify.status_code == 400
