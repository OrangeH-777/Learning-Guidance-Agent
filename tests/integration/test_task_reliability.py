import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.db.models import GenerationTask, ModelConfiguration, User
from backend.app.schemas.business import TaskCreate
from backend.app.services.tasks import create_task
from backend.app.tasks.executor import TaskExecutor
from tests.integration.test_generation_flow import prepare, request_payload


def test_concurrent_idempotency_single_user_and_global_capacity(client, app, test_engine):
    prepare(client, app, test_engine)
    with Session(test_engine) as db:
        user_id = db.scalar(select(User.id))
    payload = TaskCreate(**request_payload())
    barrier = Barrier(2)

    def create():
        barrier.wait()
        with Session(test_engine) as db, db.begin():
            return str(create_task(db, user_id, payload, app.state.settings).id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert results[0] == results[1]
    with Session(test_engine) as db:
        with pytest.raises(AppError) as failure:
            create_task(db, user_id, TaskCreate(**request_payload()), app.state.settings)
        assert failure.value.code == "BUSY"
    # Independent owners each need their own tested model and profile.
    from backend.app.db.models import ProfileRevision

    with Session(test_engine) as db, db.begin():
        original = db.scalar(select(ModelConfiguration))
        for name in ("second_user", "third_user"):
            user = User(username=name, password_hash="fixture")
            db.add(user)
            db.flush()
            db.add(
                ProfileRevision(
                    user_id=user.id,
                    course_id="data_structure",
                    version=1,
                    fields={"knowledge_base": "基础", "learning_goal": "栈", "preference": "示例"},
                )
            )
            db.add(
                ModelConfiguration(
                    user_id=user.id,
                    version=1,
                    protocol=original.protocol,
                    base_url=original.base_url,
                    model_id=original.model_id,
                    encrypted_key=original.encrypted_key,
                    tested_at=datetime.now(UTC),
                )
            )
    with Session(test_engine) as db, db.begin():
        user = db.scalar(select(User).where(User.username == "second_user"))
        create_task(db, user.id, TaskCreate(**request_payload()), app.state.settings)
    with Session(test_engine) as db:
        user = db.scalar(select(User).where(User.username == "third_user"))
        with pytest.raises(AppError) as failure:
            create_task(db, user.id, TaskCreate(**request_payload()), app.state.settings)
        assert failure.value.code == "BUSY"


async def test_scheduler_exclusion_and_restart_recovery(app, test_engine):
    from backend.app.core.config import Settings

    settings = Settings(_env_file=None)

    async def unused(task_id, deadline):
        raise AssertionError("Recovery must not automatically rerun tasks")

    with Session(test_engine) as db, db.begin():
        user = User(username="recover_user", password_hash="fixture")
        db.add(user)
        db.flush()
        model = ModelConfiguration(
            user_id=user.id,
            version=1,
            protocol="responses",
            base_url="https://fixture.invalid",
            model_id="fixture",
            encrypted_key="fixture",
        )
        db.add(model)
        db.flush()
        task = GenerationTask(
            user_id=user.id,
            course_id="data_structure",
            request_key="recover",
            request_digest="a" * 64,
            topic="栈",
            resource_type="lecture",
            profile_version=1,
            profile_snapshot={},
            model_configuration_id=model.id,
            knowledge_version="fixture",
            prompt_version="fixture",
            status="generating",
            deadline_at=datetime.now(UTC) + timedelta(seconds=180),
        )
        db.add(task)
        db.flush()
        task_id = task.id
    first, second = (
        TaskExecutor(test_engine, settings, unused),
        TaskExecutor(test_engine, settings, unused),
    )
    first.start()
    try:
        with pytest.raises(RuntimeError, match="one task scheduler"):
            second.start()
        with Session(test_engine) as db:
            restored = db.get(GenerationTask, task_id)
            assert restored.status == "failed" and restored.error_code == "INTERRUPTED"
    finally:
        await first.close()


def test_history_stable_pagination_filters_and_invalid_bounds(client, app, test_engine):
    from backend.app.db.models import Resource

    prepare(client, app, test_engine)
    with Session(test_engine) as db, db.begin():
        user_id = db.scalar(select(User.id))
        model_id = db.scalar(select(ModelConfiguration.id))
        timestamp = datetime.now(UTC)
        for i in range(12):
            task = GenerationTask(
                user_id=user_id,
                course_id="data_structure",
                request_key=str(uuid4()),
                request_digest="a" * 64,
                topic="栈" if i % 2 else "队列",
                resource_type="lecture",
                profile_version=1,
                profile_snapshot={},
                model_configuration_id=model_id,
                knowledge_version="fixture",
                prompt_version="fixture",
                status="completed",
                deadline_at=timestamp,
                finished_at=timestamp,
            )
            db.add(task)
            db.flush()
            db.add(
                Resource(
                    task_id=task.id,
                    user_id=user_id,
                    course_id=task.course_id,
                    topic=task.topic,
                    resource_type="lecture",
                    content={"title": "fixture"},
                    metadata_snapshot={},
                    source_ids=[],
                    created_at=timestamp,
                )
            )
    first, second = client.get("/api/resources").json(), client.get("/api/resources?page=2").json()
    assert len(first["items"]) == 10 and len(second["items"]) == 2
    assert len({row["id"] for row in first["items"] + second["items"]}) == 12
    assert client.get("/api/resources?topic=栈&resource_type=lecture").json()["total"] == 6
    assert client.get("/api/resources?topic=%25").json()["total"] == 0
    for query in ("page=0", "page_size=0", "page_size=51"):
        assert client.get("/api/resources?" + query).status_code == 422


async def test_two_executing_jobs_and_queued_deadline(app, test_engine):
    from backend.app.core.config import Settings

    release, started = asyncio.Event(), asyncio.Event()
    running = 0
    peak = 0
    executed = []

    async def job(task_id, budget):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        executed.append(task_id)
        if running == 2:
            started.set()
        try:
            await release.wait()
            raise AppError(422, "TEST_FINISHED", "test only")
        finally:
            running -= 1

    executor = TaskExecutor(test_engine, Settings(_env_file=None), job)
    executor.start()
    try:
        ids = []
        with Session(test_engine) as db, db.begin():
            for i in range(3):
                user = User(username=f"queue_user_{i}", password_hash="fixture")
                db.add(user)
                db.flush()
                model = ModelConfiguration(
                    user_id=user.id,
                    version=1,
                    protocol="responses",
                    base_url="https://fixture.invalid",
                    model_id="fixture",
                    encrypted_key="fixture",
                )
                db.add(model)
                db.flush()
                task = GenerationTask(
                    user_id=user.id,
                    course_id="data_structure",
                    request_key=str(uuid4()),
                    request_digest="a" * 64,
                    topic="栈",
                    resource_type="lecture",
                    profile_version=1,
                    profile_snapshot={},
                    model_configuration_id=model.id,
                    knowledge_version="fixture",
                    prompt_version="fixture",
                    status="queued",
                    deadline_at=datetime.now(UTC) + timedelta(seconds=5),
                )
                db.add(task)
                db.flush()
                ids.append(task.id)
        executor.submit(ids[0])
        executor.submit(ids[1])
        await asyncio.wait_for(started.wait(), 2)
        with Session(test_engine) as db, db.begin():
            db.get(GenerationTask, ids[2]).deadline_at = datetime.now(UTC) + timedelta(seconds=0.1)
        executor.submit(ids[2])
        executor.submit(ids[0])  # Duplicate delivery must not execute twice.
        await asyncio.wait_for(asyncio.shield(executor._jobs[ids[2]]), 2)
        with Session(test_engine) as db:
            queued = db.get(GenerationTask, ids[2])
            assert queued.status == "failed" and queued.error_code == "TASK_TIMEOUT"
        assert peak == 2 and set(executed) == set(ids[:2]) and len(executed) == 2
        release.set()
        await asyncio.gather(*list(executor._jobs.values()))
        with Session(test_engine) as db:
            assert all(
                db.get(GenerationTask, task_id).error_code == "TEST_FINISHED" for task_id in ids[:2]
            )
    finally:
        release.set()
        await executor.close()
