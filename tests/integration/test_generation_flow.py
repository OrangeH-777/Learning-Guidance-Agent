import json
import time
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.schemas.models import ModelResponse
from backend.app.db.models import (
    Course,
    GenerationTask,
    KnowledgeChunk,
    KnowledgeDocument,
    Resource,
    ValidationRecord,
)
from tests.integration.conftest import register

FIXTURES = json.loads(
    (Path(__file__).parents[1] / "fixtures/resource_contracts.json").read_text(encoding="utf-8")
)["resources"]
FIELDS = {"knowledge_base": "初学者", "learning_goal": "掌握栈", "preference": "具体示例"}


class FakeEmbedder:
    model_id = "test-embedding"
    dimensions = 3

    async def embed(self, texts, *, timeout_seconds):
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeProvider:
    """Only tests install this factory; it is never available through deployment configuration."""

    def __init__(self, *, bad=False):
        self.bad = bad
        self.calls = []

    async def generate(self, request, *, timeout_seconds):
        self.calls.append(request)
        content = request.messages[-1].content
        if "连接测试" in content:
            return ModelResponse(text="OK", model_id="fixture-model")
        data = json.loads(content)
        if "statement" in data:
            result = {**FIELDS, "conflicts": []}
        elif "candidate" in data:
            result = {
                "relevant": True,
                "supported": True,
                "facts_correct": True,
                "answers_consistent": True,
                "safe": True,
                "issues": [],
            }
        elif "plan" in data:
            result = deepcopy(
                next(r for r in FIXTURES if r["resource_type"] == data["resource_type"])
            )
            result["source_ids"] = [str(uuid4())] if self.bad else [data["sources"][0]["id"]]
        else:
            result = {
                "objectives": ["理解栈"],
                "difficulty": "入门",
                "prerequisites": ["线性序列"],
                "outline": ["后进先出", "括号匹配"],
                "personalization": "提供逐步操作示例",
            }
        return ModelResponse(text=json.dumps(result, ensure_ascii=False), model_id="fixture-model")


def prepare(client, app, engine, *, bad=False):
    register(client)
    provider = FakeProvider(bad=bad)
    app.state.provider_factory = lambda config, settings: provider
    app.state.embedder_factory = lambda settings: FakeEmbedder()
    app.state.settings.embedding_index_version = "fixture-index"
    with Session(engine) as db:
        course = db.get(Course, "data_structure")
        course.active_index_version = "fixture-index"
        document = KnowledgeDocument(
            course_id=course.id,
            visibility="public",
            owner_id=None,
            source_key="fixture",
            title="TEST ONLY",
            locator="fixture:stack",
            license="test fixture",
            content_hash="a" * 64,
            version="fixture-v1",
        )
        db.add(document)
        db.flush()
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                ordinal=0,
                locator="fixture:stack",
                content="栈后进先出，括号匹配可用栈。此条目仅用于自动测试。",
                index_version="fixture-index",
                embedding_model="test-embedding",
                dimensions=3,
                embedding=[1, 0, 0],
            )
        )
        db.commit()
    assert (
        client.put(
            "/api/model-settings",
            json={
                "expected_version": 0,
                "protocol": "responses",
                "base_url": "https://fixture.invalid/v1",
                "model_id": "fixture-model",
                "api_key": "test-secret",
            },
        ).status_code
        == 200
    )
    assert client.post("/api/model-settings/test").status_code == 200
    assert (
        client.put(
            "/api/courses/data_structure/profile", json={**FIELDS, "expected_version": 0}
        ).status_code
        == 200
    )
    return provider


def request_payload(resource_type="lecture"):
    return {
        "course_id": "data_structure",
        "topic": "栈与括号匹配",
        "resource_type": resource_type,
        "profile_version": 1,
        "model_version": 1,
        "request_key": str(uuid4()),
    }


def wait_task(client, task_id):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        result = client.get(f"/api/tasks/{task_id}")
        assert result.status_code == 200
        if result.json()["status"] in {"failed", "completed"}:
            return result.json()
        time.sleep(0.02)
    pytest.fail("Task did not reach a terminal state")


@pytest.mark.parametrize("kind", ["lecture", "exercise", "mindmap"])
def test_end_to_end_with_real_postgres_and_explicit_model_double(client, app, test_engine, kind):
    prepare(client, app, test_engine)
    payload = request_payload(kind)
    accepted = client.post("/api/tasks", json=payload)
    assert accepted.status_code == 202, accepted.text
    task = wait_task(client, accepted.json()["id"])
    assert task["status"] == "completed", task
    assert task["telemetry"]["model_attempts"] == 4
    assert task["content_regenerations"] == 0
    assert "test-secret" not in json.dumps(task)
    resource = client.get(f"/api/resources/{task['resource_id']}").json()
    assert resource["content"]["resource_type"] == kind
    assert resource["human_pass"] is False and "由AI生成" in resource["notice"]
    assert client.get("/api/resources").json()["total"] == 1
    assert client.post("/api/tasks", json=payload).json()["id"] == task["id"]
    assert client.post("/api/tasks", json={**payload, "topic": "different"}).status_code == 409
    source = resource["content"]["source_ids"][0]
    assert client.get(f"/api/courses/data_structure/sources/{source}").status_code == 200
    assert client.get(f"/api/courses/test_course/sources/{source}").status_code == 404
    other = TestClient(app)
    register(other, "learner_b")
    assert other.get(f"/api/tasks/{task['id']}").status_code == 404
    assert other.get(f"/api/resources/{task['resource_id']}").status_code == 404
    assert other.get("/api/resources").json()["total"] == 0
    # Configuration edits leave persisted task/resource snapshots unchanged.
    client.put(
        "/api/courses/data_structure/profile",
        json={**FIELDS, "preference": "证明推导", "expected_version": 1},
    )
    assert (
        client.get(f"/api/resources/{task['resource_id']}").json()["metadata"]["profile"]["version"]
        == 1
    )
    with Session(test_engine) as db:
        assert len(list(db.scalars(select(ValidationRecord)))) == 2
        observed = db.get(GenerationTask, accepted.json()["id"])
        telemetry = observed.telemetry
        assert telemetry["task_id"] == task["id"]
        assert telemetry["prompt_version"] == resource["metadata"]["prompt_version"]
        assert telemetry["model_attempts"] == 4
        assert {span["node"] for span in telemetry["nodes"]} == {
            "planning",
            "generating",
            "validating",
            "formatting",
        }
        assert all(span["elapsed_seconds"] >= 0 for span in telemetry["nodes"])
        assert "test-secret" not in json.dumps(telemetry)
        assert "profile" not in telemetry


def test_rejected_sources_retry_limit_no_history_and_manual_retry(client, app, test_engine):
    provider = prepare(client, app, test_engine, bad=True)
    task_id = client.post("/api/tasks", json=request_payload()).json()["id"]
    failed = wait_task(client, task_id)
    assert failed["status"] == "failed" and failed["error_code"] == "CONTENT_REJECTED"
    assert client.get("/api/resources").json()["total"] == 0
    with Session(test_engine) as db:
        task = db.scalar(select(GenerationTask))
        assert task.content_regenerations == 2
        assert len([s for s in task.telemetry["nodes"] if s["node"] == "generating"]) == 3
    provider.bad = False
    request = {"request_key": str(uuid4())}
    retry = client.post(f"/api/tasks/{task_id}/retry", json=request)
    assert retry.status_code == 202, retry.text
    assert wait_task(client, retry.json()["id"])["status"] == "completed"
    assert retry.json()["parent_task_id"] == task_id
    assert (
        client.post(f"/api/tasks/{task_id}/retry", json=request).json()["id"] == retry.json()["id"]
    )


def test_conversation_is_draft_until_user_confirms(client, app, test_engine):
    prepare(client, app, test_engine)
    url = "/api/courses/data_structure/profile"
    result = client.post(
        url + "/conversation", json={"content": "我想学习栈", "expected_revision": 0}
    )
    assert result.status_code == 200, result.text
    assert result.json()["revision"] == 1 and result.json()["missing"] == []
    assert client.get(url).json()["version"] == 1
    assert client.get("/api/courses/test_course/profile/draft").json()["revision"] == 0
    assert (
        client.post(
            url + "/conversation", json={"content": "stale", "expected_revision": 0}
        ).status_code
        == 409
    )


def test_publish_rollback_keeps_no_resource_or_completed_status(client, app, test_engine):
    from backend.app.db.models import User
    from backend.app.schemas.business import TaskCreate
    from backend.app.services.tasks import create_task, publish_resource

    prepare(client, app, test_engine)
    with Session(test_engine) as db:
        task = create_task(
            db, db.scalar(select(User.id)), TaskCreate(**request_payload()), app.state.settings
        )
        task.status = "formatting"
        db.commit()
        task_id = task.id
    with pytest.raises(RuntimeError):
        with Session(test_engine) as db, db.begin():
            publish_resource(db, task_id, FIXTURES[0], {})
            raise RuntimeError("injected commit failure")
    with Session(test_engine) as db:
        assert db.get(GenerationTask, task_id).status == "formatting"
        assert db.scalar(select(Resource)) is None


def test_unavailable_prompt_version_fails_without_model_call(client, app, test_engine):
    from backend.app.db.models import User
    from backend.app.schemas.business import TaskCreate
    from backend.app.services.tasks import create_task

    provider = prepare(client, app, test_engine)
    with Session(test_engine) as db, db.begin():
        task = create_task(
            db, db.scalar(select(User.id)), TaskCreate(**request_payload()), app.state.settings
        )
        task.prompt_version = "obsolete-version"
        task.status = "failed"
        task.error_code = "INTERRUPTED"
        task_id = task.id
    before = len(provider.calls)
    retry = client.post(f"/api/tasks/{task_id}/retry", json={"request_key": str(uuid4())})
    assert retry.status_code == 202
    result = wait_task(client, retry.json()["id"])
    assert result["status"] == "failed"
    assert result["error_code"] == "PROMPT_VERSION_UNAVAILABLE"
    assert len(provider.calls) == before
    assert client.get("/api/resources").json()["total"] == 0


def test_disabled_course_keeps_history_and_sources_but_refuses_new_tasks(client, app, test_engine):
    prepare(client, app, test_engine)
    result = client.post("/api/tasks", json=request_payload())
    task = wait_task(client, result.json()["id"])
    assert task["status"] == "completed"
    before = client.get(f"/api/resources/{task['resource_id']}").json()
    source_id = before["content"]["source_ids"][0]
    with Session(test_engine) as db, db.begin():
        db.get(Course, "data_structure").enabled = False
    assert client.post("/api/tasks", json=request_payload()).status_code == 409
    assert client.get(f"/api/resources/{task['resource_id']}").json() == before
    assert client.get(f"/api/courses/data_structure/sources/{source_id}").status_code == 200
    assert client.get("/api/resources?course_id=data_structure").json()["total"] == 1


def test_private_source_and_draft_are_unavailable_to_other_users(client, app, test_engine):
    from backend.app.db.models import User

    prepare(client, app, test_engine)
    assert (
        client.post(
            "/api/courses/data_structure/profile/conversation",
            json={"content": "个人学习情况", "expected_revision": 0},
        ).status_code
        == 200
    )
    with Session(test_engine) as db, db.begin():
        owner_id = db.scalar(select(User.id))
        document = db.scalar(select(KnowledgeDocument))
        document.visibility = "private"
        document.owner_id = owner_id
        source_id = db.scalar(select(KnowledgeChunk.id))
    other = TestClient(app)
    register(other, "learner_b")
    path = f"/api/courses/data_structure/sources/{source_id}"
    assert client.get(path).status_code == 200
    assert other.get(path).status_code == 404
    assert other.get("/api/courses/data_structure/profile/draft").json()["revision"] == 0
    assert (
        other.put(
            "/api/courses/data_structure/profile",
            json={**FIELDS, "expected_version": 0, "user_id": str(owner_id)},
        ).status_code
        == 422
    )
