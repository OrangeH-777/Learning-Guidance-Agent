from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import LoginSession, ModelConfiguration, User
from tests.integration.conftest import register

FIELDS = {"knowledge_base": "了解数组", "learning_goal": "学习栈", "preference": "结合示例"}


def test_registration_session_password_and_logout(client, test_engine):
    data = register(client, "Learner_A")
    assert data["user"]["username"] == "learner_a"
    assert client.get("/api/auth/session").status_code == 200
    with Session(test_engine) as db:
        user = db.scalar(select(User))
        login = db.scalar(select(LoginSession))
        assert user.password_hash.startswith("$argon2id$")
        assert "Study2026" not in user.password_hash
        assert login.token_hash != client.cookies.get("lga_session")
    token = client.cookies.get("lga_session")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("lga_session", token)
    assert client.get("/api/auth/session").status_code == 401


def test_duplicate_normalized_username_and_uniform_login_error(client):
    register(client)
    result = client.post(
        "/api/auth/register",
        json={
            "username": "LEARNER_A",
            "password": "Study2026",
            "password_confirmation": "Study2026",
        },
    )
    assert result.status_code == 409
    errors = [
        client.post("/api/auth/login", json={"username": name, "password": "Wrong2026"})
        for name in ("learner_a", "nobody_1")
    ]
    assert errors[0].status_code == errors[1].status_code == 401
    assert errors[0].json() == errors[1].json()


def test_csrf_origin_and_expiry(client, test_engine):
    register(client)
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert (
        client.post("/api/auth/logout", headers={"Origin": "https://evil.invalid"}).status_code
        == 403
    )
    with Session(test_engine) as db:
        db.scalar(select(LoginSession)).expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/auth/session").status_code == 401


def test_profile_course_and_user_isolation(client, app):
    register(client)
    url = "/api/courses/data_structure/profile"
    result = client.put(url, json={**FIELDS, "expected_version": 0})
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 1
    assert client.get("/api/courses/test_course/profile").json()["version"] == 0
    # Do not enter a second lifespan: it would reset the shared application's state.
    other = TestClient(app)
    register(other, "learner_b")
    assert other.get(url).json()["version"] == 0
    assert client.put(url, json={**FIELDS, "expected_version": 1}).json()["version"] == 1
    assert client.put(url, json={**FIELDS, "expected_version": 0}).status_code == 409
    assert (
        client.put(url, json={**FIELDS, "preference": "逐步推导", "expected_version": 1}).json()[
            "version"
        ]
        == 2
    )
    assert other.get(url).json()["version"] == 0


def test_model_key_encryption_versions_and_user_isolation(client, app, test_engine):
    register(client)
    payload = {
        "expected_version": 0,
        "protocol": "responses",
        "base_url": "https://api.example.com/v1",
        "model_id": "chosen-model",
        "api_key": "secret_test_key",
    }
    result = client.put("/api/model-settings", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["has_key"] is True
    assert "secret_test_key" not in result.text
    with Session(test_engine) as db:
        assert db.scalar(select(ModelConfiguration)).encrypted_key != "secret_test_key"
    other = TestClient(app)
    register(other, "learner_b")
    assert other.get("/api/model-settings").json() == {"version": 0, "configured": False}
    assert client.put("/api/model-settings", json=payload).status_code == 409
    assert client.delete("/api/model-settings").status_code == 204
    assert not client.get("/api/model-settings").json()["configured"]


def test_auth_required_and_invalid_payload_never_echoes_key(client):
    assert client.get("/api/courses").status_code == 401
    register(client)
    result = client.put("/api/model-settings", json={"api_key": "supersecret"})
    assert result.status_code == 422
    assert "supersecret" not in result.text
