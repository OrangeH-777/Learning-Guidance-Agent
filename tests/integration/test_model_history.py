from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import ModelConfiguration
from backend.app.services.models import cipher
from tests.integration.conftest import register


def test_model_values_are_explicit_and_history_is_owned_paginated_and_secret_free(
    client, app, test_engine
):
    assert client.get("/api/model-settings/history").status_code == 401
    owner = register(client, "history_owner")
    assert client.get("/api/model-settings").json() == {"version": 0, "configured": False}
    assert client.get("/api/model-settings/history").json()["items"] == []
    with Session(test_engine) as db:
        assert db.scalar(select(func.count()).select_from(ModelConfiguration)) == 0
    base = {"protocol": "responses", "base_url": "https://example.org/v1", "model_id": "chosen"}
    assert (
        client.put("/api/model-settings", json={**base, "expected_version": 0}).status_code == 422
    )
    for version in range(12):
        response = client.put(
            "/api/model-settings",
            json={
                **base,
                "model_id": f"chosen-{version}",
                "expected_version": version,
                "api_key": f"provider-secret-{version}",
            },
        )
        assert response.status_code == 200
    first = client.get("/api/model-settings/history").json()
    assert first["total"] == 12 and len(first["items"]) == 10
    assert [row["version"] for row in first["items"]] == list(range(12, 2, -1))
    assert first["items"][0]["model_id"] == "chosen-11"
    second = client.get("/api/model-settings/history?page=2").json()
    assert [row["version"] for row in second["items"]] == [2, 1]
    encoded = str(first) + str(second)
    assert all(
        secret not in encoded
        for secret in (
            "provider-secret",
            "encrypted_key",
            "Study2026",
            "password_hash",
            "history_owner",
        )
    )
    other = TestClient(app)
    register(other, "history_other")
    assert (
        other.get(f"/api/model-settings/history?user_id={owner['user']['id']}").json()["items"]
        == []
    )
    assert (
        other.put(
            "/api/model-settings",
            json={
                **base,
                "expected_version": 0,
                "model_id": "other-only",
                "api_key": "other-token",
            },
        ).status_code
        == 200
    )
    assert other.get("/api/model-settings/history").json()["total"] == 1
    assert "other-only" not in client.get("/api/model-settings/history").text
    with Session(test_engine) as db:
        configs = db.scalars(select(ModelConfiguration)).all()
        keys = [cipher(app.state.settings).decrypt(c.encrypted_key) for c in configs]
        assert "provider-secret-11" in keys and "other-token" in keys and "Study2026" not in keys
    assert client.get("/api/model-settings/history?page=0").status_code == 422
    assert client.get("/api/model-settings/history?page_size=51").status_code == 422
    assert client.delete("/api/model-settings").status_code == 204
    retired = client.get("/api/model-settings/history").json()
    assert retired["total"] == 13
    assert retired["items"][0]["configured"] is False and not retired["items"][0]["has_key"]
