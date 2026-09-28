import asyncio
import json

from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from agents.schemas.models import ModelResponse
from tests.integration.test_generation_flow import FIELDS, prepare

PROFILE = "/api/courses/data_structure/profile"


class ExtractionReply:
    def __init__(self, value):
        self.text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    async def generate(self, request, *, timeout_seconds):
        return ModelResponse(text=self.text, model_id="fixture")


def test_missing_information_is_requested_without_default_or_confirmation(client, app, test_engine):
    prepare(client, app, test_engine)
    provider = ExtractionReply({"learning_goal": "学习栈", "conflicts": []})
    app.state.provider_factory = lambda config, settings: provider
    response = client.post(
        PROFILE + "/conversation", json={"content": "我要学栈", "expected_revision": 0}
    )
    assert response.status_code == 200
    draft = response.json()
    assert draft["fields"] == {"learning_goal": "学习栈"}
    assert set(draft["missing"]) == {"知识基础", "学习偏好"}
    assert client.get(PROFILE).json() == {"version": 1, "fields": FIELDS}


def test_conflict_keeps_previous_draft_and_confirmed_profile(client, app, test_engine):
    prepare(client, app, test_engine)
    first = client.post(
        PROFILE + "/conversation", json={"content": "学习栈", "expected_revision": 0}
    ).json()
    provider = ExtractionReply(
        {**FIELDS, "knowledge_base": "熟练", "conflicts": ["与之前基础描述冲突"]}
    )
    app.state.provider_factory = lambda config, settings: provider
    response = client.post(
        PROFILE + "/conversation", json={"content": "我熟练了", "expected_revision": 1}
    )
    assert response.status_code == 200
    assert response.json()["fields"] == first["fields"]
    assert response.json()["conflicts"]
    assert client.get(PROFILE).json()["version"] == 1


def test_invalid_model_json_preserves_draft_and_profile(client, app, test_engine):
    prepare(client, app, test_engine)
    before = client.get(PROFILE + "/draft").json()
    app.state.provider_factory = lambda config, settings: ExtractionReply(
        "invalid-json-secret-canary"
    )
    response = client.post(
        PROFILE + "/conversation", json={"content": "学习栈", "expected_revision": 0}
    )
    assert response.status_code == 502 and "secret-canary" not in response.text
    assert client.get(PROFILE + "/draft").json() == before
    assert client.get(PROFILE).json() == {"version": 1, "fields": FIELDS}


def test_draft_save_failure_rolls_back_without_confirming_profile(client, app, test_engine):
    prepare(client, app, test_engine)
    engine = app.state.database_engine

    def fail_save(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO profile_drafts"):
            raise OperationalError("fixture", {}, RuntimeError("private-error-canary"))

    event.listen(engine, "before_cursor_execute", fail_save)
    try:
        response = client.post(
            PROFILE + "/conversation", json={"content": "学习栈", "expected_revision": 0}
        )
    finally:
        event.remove(engine, "before_cursor_execute", fail_save)
    assert response.status_code == 503 and "private-error-canary" not in response.text
    assert client.get(PROFILE + "/draft").json()["revision"] == 0
    assert client.get(PROFILE).json() == {"version": 1, "fields": FIELDS}


def test_interactive_deadline_rejects_late_reply_and_invalidates_connection_test(
    client, app, test_engine
):
    from tests.integration.test_generation_flow import request_payload

    prepare(client, app, test_engine)

    class LateReply:
        async def generate(self, request, *, timeout_seconds):
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                return ModelResponse(text=json.dumps(FIELDS), model_id="late-fixture")

    app.state.provider_factory = lambda config, settings: LateReply()
    app.state.settings.model_call_timeout_seconds = 0.01
    result = client.post(
        PROFILE + "/conversation", json={"content": "学习栈", "expected_revision": 0}
    )
    assert result.status_code == 502 and result.json()["error"]["code"] == "MODEL_TIMEOUT"
    assert client.get(PROFILE + "/draft").json()["revision"] == 0
    result = client.post("/api/model-settings/test")
    assert result.status_code == 502 and result.json()["error"]["code"] == "MODEL_TIMEOUT"
    assert client.get("/api/model-settings").json()["tested_at"] is None
    assert (
        client.post("/api/tasks", json=request_payload()).json()["error"]["code"]
        == "MODEL_NOT_TESTED"
    )
