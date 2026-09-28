import asyncio
import shutil
import time
from types import SimpleNamespace
from uuid import UUID

import pytest
import yaml
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.retrieval.catalog import read_course
from agents.retrieval.vector import search
from agents.workflows.runtime import Deadline
from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.core.errors import AppError
from backend.app.core.security import verify_password
from backend.app.db.models import Course, KnowledgeChunk, User
from backend.app.services.knowledge import compatible_index, retrieve_context
from backend.app.services.public_knowledge import PublicKnowledgeManager
from scripts.bootstrap_admin import bootstrap_admin
from tests.integration.conftest import register
from tests.integration.test_generation_flow import FakeEmbedder
from tests.unit.test_material_text import pdf_bytes, word_bytes


@pytest.fixture
def admin(client, test_engine, tmp_path):
    identity = register(client, "admin_test")
    with Session(test_engine) as db, db.begin():
        db.get(User, UUID(identity["user"]["id"])).is_admin = True
    root = tmp_path / "knowledge"
    shutil.copytree(PROJECT_ROOT / "knowledge/data_structure", root / "data_structure")
    shutil.copytree(root / "data_structure", root / "test_course")
    other = root / "test_course/course.yaml"
    value = yaml.safe_load(other.read_text(encoding="utf-8"))
    value["id"] = "test_course"
    other.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
    with Session(test_engine) as db, db.begin():
        for name in ("data_structure", "test_course"):
            db.get(Course, name).content_version = read_course(root / name).version
    settings = client.app.state.settings
    settings.public_knowledge_dir = str(root)
    settings.embedding_index_version = "admin-fixture"
    client.app.state.public_knowledge = PublicKnowledgeManager(
        test_engine, settings, lambda config: FakeEmbedder()
    )
    return client


def payload(client, **overrides):
    course = client.get("/api/admin/courses").json()[0]
    return {
        "expected_version": course["version"],
        "title": "原创示例教材",
        "source_url": "https://example.org/book",
        "section": "第一章",
        "license": "测试原创",
        "content": "# 栈\n\n栈后进先出；括号匹配在遇到不匹配的右括号时失败。",
        "confirmed": True,
        **overrides,
    }


def wait_index(client):
    for _ in range(100):
        job = client.get("/api/admin/index").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    pytest.fail("Index job did not finish")


def test_admin_bootstrap_is_idempotent_hashes_password_and_never_promotes(app, test_engine):
    settings = Settings(_env_file=None, admin_username="LOCAL_ADMIN", admin_password="Secret1234")
    assert bootstrap_admin(test_engine, settings) == "created"
    settings.admin_password = SecretStr("Changed1234")
    assert bootstrap_admin(test_engine, settings) == "unchanged"
    with Session(test_engine) as db, db.begin():
        user = db.scalar(select(User).where(User.username == "local_admin"))
        assert user.is_admin and verify_password(user.password_hash, "Secret1234")
        assert not verify_password(user.password_hash, "Changed1234")
        user.is_admin = False
    with pytest.raises(ValueError, match="non-administrator"):
        bootstrap_admin(test_engine, settings)


def test_anonymous_normal_user_csrf_and_role_spoof_are_rejected(client):
    assert client.get("/api/admin/courses").status_code == 401
    user = register(client)
    assert user["user"]["is_admin"] is False
    assert client.get("/api/admin/courses").status_code == 403
    assert (
        client.post("/api/admin/materials/preview?filename=book.md", content=b"# no").status_code
        == 403
    )
    forged = client.post(
        "/api/auth/register",
        json={
            "username": "evil_admin",
            "password": "Password1",
            "password_confirmation": "Password1",
            "is_admin": True,
        },
    )
    assert forged.status_code == 422
    client.app.state.settings.admin_username = "reserved_admin"
    assert (
        client.post(
            "/api/auth/register",
            json={
                "username": "reserved_admin",
                "password": "Password1",
                "password_confirmation": "Password1",
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "name,data",
    [("book.md", b"# Stack\n\nLIFO"), ("book.pdf", pdf_bytes()), ("book.docx", word_bytes())],
    ids=["markdown", "pdf", "word"],
)
def test_upload_preview_then_save_and_review_is_explicit(admin, name, data):
    before = admin.get("/api/admin/courses").json()[0]
    result = admin.post("/api/admin/materials/preview", params={"filename": name}, content=data)
    assert result.status_code == 200, result.text
    assert admin.get("/api/admin/courses").json()[0] == before
    values = payload(admin, content=result.json()["content"])
    assert (
        admin.post(
            "/api/admin/courses/data_structure/materials", json={**values, "confirmed": False}
        ).status_code
        == 422
    )
    saved = admin.post("/api/admin/courses/data_structure/materials", json=values)
    assert saved.status_code == 201, saved.text
    detail = admin.get(f"/api/admin/courses/data_structure/materials/{saved.json()['source_id']}")
    assert detail.json()["content"] == result.json()["content"]
    assert detail.json()["review_status"] == "approved"
    assert admin.post("/api/admin/courses/data_structure/materials", json=values).status_code == 409
    other = admin.get("/api/admin/courses").json()[1]
    assert len(other["sources"]) == len(before["sources"])


def test_preview_limits_csrf_and_no_path_from_filename(admin):
    assert admin.get("/api/auth/session").json()["user"]["is_admin"] is True
    response = admin.post(
        "/api/admin/materials/preview?filename=book.md", content=b"A" * (10 * 1024 * 1024 + 1)
    )
    assert response.status_code == 413
    assert (
        admin.post("/api/admin/materials/preview?filename=old.doc", content=b"data").status_code
        == 422
    )
    response = admin.post(
        "/api/admin/materials/preview?filename=../../outside.md", content=b"# Safe"
    )
    assert response.status_code == 200
    assert not (admin.app.state.public_knowledge.root.parent / "outside.md").exists()
    admin.headers.pop("X-CSRF-Token")
    assert (
        admin.post("/api/admin/materials/preview?filename=book.md", content=b"# hi").status_code
        == 403
    )


def test_index_roundtrip_real_pgvector_retains_history_and_is_course_scoped(admin, test_engine):
    settings = admin.app.state.settings
    version = payload(admin)["expected_version"]
    request = {"expected_version": version, "acknowledge_costs": True}
    assert admin.post("/api/admin/courses/data_structure/index", json=request).status_code == 409
    request["allow_unreviewed"] = True
    assert admin.post("/api/admin/courses/data_structure/index", json=request).status_code == 202
    first = wait_index(admin)
    assert first["status"] == "indexed" and first["chunks"] > 6
    assert compatible_index(first["index_version"], settings)
    with Session(test_engine) as db:
        admin_user = db.scalar(select(User))
        found = search(
            db,
            user_id=admin_user.id,
            course_id="data_structure",
            index_version=first["index_version"],
            model_id="test-embedding",
            vector=[1, 0, 0],
            dimensions=3,
            limit=50,
            max_cosine_distance=0.1,
        )
        assert any("后进先出" in fragment.content for fragment in found)
        assert not search(
            db,
            user_id=admin_user.id,
            course_id="test_course",
            index_version=first["index_version"],
            model_id="test-embedding",
            vector=[1, 0, 0],
            dimensions=3,
            limit=50,
            max_cosine_distance=0.1,
        )
        context = SimpleNamespace(
            user_id=admin_user.id,
            course_id="data_structure",
            knowledge_version=first["index_version"],
            topic="栈与队列",
        )
    retrieved = asyncio.run(
        retrieve_context(
            test_engine,
            context,
            settings,
            Deadline(10),
            lambda config: FakeEmbedder(),
        )
    )
    assert retrieved
    saved = admin.post("/api/admin/courses/data_structure/materials", json=payload(admin))
    assert saved.status_code == 201
    request["expected_version"] = saved.json()["version"]
    assert admin.post("/api/admin/courses/data_structure/index", json=request).status_code == 202
    second = wait_index(admin)
    assert second["status"] == "indexed" and second["index_version"] != first["index_version"]
    with Session(test_engine) as db:
        assert db.get(Course, "data_structure").active_index_version == second["index_version"]
        assert db.scalar(
            select(KnowledgeChunk).where(KnowledgeChunk.index_version == first["index_version"])
        )
    settings.embedding_index_version = "another-family"
    assert not compatible_index(first["index_version"], settings)
    with pytest.raises(AppError, match="INDEX_VERSION_UNAVAILABLE"):
        asyncio.run(
            retrieve_context(
                test_engine,
                context,
                settings,
                Deadline(10),
                lambda config: FakeEmbedder(),
            )
        )


def test_index_failure_keeps_old_index_and_does_not_leak_provider_details(admin, test_engine):
    with Session(test_engine) as db, db.begin():
        db.get(Course, "data_structure").active_index_version = "old-index"

    class FailedEmbedder(FakeEmbedder):
        async def embed(self, texts, *, timeout_seconds):
            await asyncio.sleep(0.1)
            raise RuntimeError("private-provider-token")

    manager = admin.app.state.public_knowledge
    manager.embedder_factory = lambda settings: FailedEmbedder()
    values = payload(admin)
    result = admin.post(
        "/api/admin/courses/data_structure/index",
        json={
            "expected_version": values["expected_version"],
            "acknowledge_costs": True,
            "allow_unreviewed": True,
        },
    )
    assert result.status_code == 202
    assert admin.post("/api/admin/courses/data_structure/materials", json=values).status_code == 409
    failed = wait_index(admin)
    assert failed["status"] == "failed" and "private-provider-token" not in str(failed)
    with Session(test_engine) as db:
        assert db.get(Course, "data_structure").active_index_version == "old-index"
    assert "private-provider-token" not in manager.state_file.read_text(encoding="utf-8")


def test_failed_database_commit_restores_catalog_and_restart_marks_interrupted(admin, monkeypatch):
    from unittest.mock import patch

    manager = admin.app.state.public_knowledge
    directory = manager.root / "data_structure"
    before = (directory / "course.yaml").read_bytes()
    files = set(directory.rglob("*"))
    values = payload(admin)
    from backend.app.schemas.materials import IndexJob, MaterialSave

    with patch(
        "sqlalchemy.orm.session.SessionTransaction.commit", side_effect=RuntimeError("db failed")
    ):
        with pytest.raises(RuntimeError):
            manager.save("data_structure", MaterialSave.model_validate(values))
    assert (directory / "course.yaml").read_bytes() == before
    assert set(directory.rglob("*")) == files
    manager.job = IndexJob(
        id="restart-test", course_id="data_structure", index_version="demo", status="running"
    )
    manager.persist_job()
    restored = PublicKnowledgeManager(manager.engine, manager.settings, manager.embedder_factory)
    assert restored.job.status == "interrupted"
