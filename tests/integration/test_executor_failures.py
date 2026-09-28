import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.db.models import GenerationTask, ModelConfiguration, Resource, User
from backend.app.tasks.executor import TaskExecutor


def seed_task(engine, seconds=5):
    with Session(engine) as db, db.begin():
        user = User(username="failure_test", password_hash="fixture")
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
            request_key="failure-test",
            request_digest="a" * 64,
            topic="栈",
            resource_type="lecture",
            profile_version=1,
            profile_snapshot={},
            model_configuration_id=model.id,
            knowledge_version="fixture",
            prompt_version="fixture",
            status="queued",
            deadline_at=datetime.now(UTC) + timedelta(seconds=seconds),
        )
        db.add(task)
        db.flush()
        return task.id


@pytest.mark.parametrize("mode,code", [("save", "SAVE_FAILED"), ("late", "TASK_TIMEOUT")])
async def test_executor_persists_failure_and_discards_late_result(app, test_engine, mode, code):
    async def job(task_id, budget):
        if mode == "save":
            raise OperationalError("fixture", {}, RuntimeError("secret-canary"))
        try:
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            await asyncio.sleep(0.01)
            return "late provider result"

    executor = TaskExecutor(test_engine, Settings(_env_file=None), job)
    executor.start()
    try:
        task_id = seed_task(test_engine, seconds=0.05 if mode == "late" else 5)
        executor.submit(task_id)
        await asyncio.wait_for(asyncio.shield(executor._jobs[task_id]), 2)
        with Session(test_engine) as db:
            task = db.get(GenerationTask, task_id)
            assert task.status == "failed" and task.error_code == code
            assert task.finished_at is not None
            assert db.scalar(select(Resource)) is None
    finally:
        await executor.close()


async def test_deferred_failure_is_persisted_after_database_recovers(app, test_engine, caplog):
    async def unused(task_id, budget):
        raise AssertionError("Failure persistence must not rerun a model")

    executor = TaskExecutor(test_engine, Settings(_env_file=None), unused)
    executor.start()
    task_id = seed_task(test_engine)

    def outage(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE generation_tasks"):
            raise OperationalError("fixture", {}, RuntimeError("database-secret-canary"))

    try:
        event.listen(test_engine, "before_cursor_execute", outage)
        try:
            executor._fail(task_id, "SAVE_FAILED")
        finally:
            event.remove(test_engine, "before_cursor_execute", outage)
        assert executor._pending_failures == {task_id: "SAVE_FAILED"}
        with Session(test_engine) as db:
            assert db.get(GenerationTask, task_id).status == "queued"
        executor._fail(task_id, "SAVE_FAILED")
        with Session(test_engine) as db:
            assert db.get(GenerationTask, task_id).status == "failed"
        assert not executor._pending_failures and "database-secret-canary" not in caplog.text
    finally:
        await executor.close()
