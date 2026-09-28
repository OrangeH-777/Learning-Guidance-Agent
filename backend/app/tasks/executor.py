"""One scheduler per database; unfinished tasks become INTERRUPTED on restart."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agents.schemas.models import ModelFailure
from agents.workflows.runtime import Deadline, TaskDeadlineExceeded
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.db.models import GenerationTask
from backend.app.tasks.state import TERMINAL_STATUSES

logger = logging.getLogger(__name__)
Job = Callable[[UUID, Deadline], Awaitable[None]]


class TaskExecutor:
    def __init__(self, engine: Engine, settings: Settings, job: Job):
        self.engine, self.settings, self.job = engine, settings, job
        self._semaphore = asyncio.Semaphore(settings.global_generation_limit)
        self._jobs: dict[UUID, asyncio.Task] = {}
        self._pending_failures: dict[UUID, str] = {}
        self._lock_connection = None
        self._monitor: asyncio.Task | None = None
        self.ready = False

    def start(self):
        self._lock_connection = self.engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        )
        if not self._lock_connection.scalar(text("SELECT pg_try_advisory_lock(724905182)")):
            self._lock_connection.close()
            self._lock_connection = None
            raise RuntimeError("Only one task scheduler may run against this database")
        try:
            with Session(self.engine) as db, db.begin():
                db.execute(
                    update(GenerationTask)
                    .where(GenerationTask.status.not_in(TERMINAL_STATUSES))
                    .values(
                        status="failed", error_code="INTERRUPTED", finished_at=datetime.now(UTC)
                    )
                )
            self.ready = True
            self._monitor = asyncio.create_task(self._sweep())
        except BaseException:
            self._release_lock()
            raise

    def submit(self, task_id: UUID):
        if not self.ready:
            raise AppError(503, "NOT_READY", "任务执行器尚未就绪")
        if task_id not in self._jobs:
            task = asyncio.create_task(self._run(task_id))
            self._jobs[task_id] = task
            task.add_done_callback(lambda _: self._jobs.pop(task_id, None))

    async def _run(self, task_id: UUID):
        try:
            with Session(self.engine) as db:
                task = db.get(GenerationTask, task_id)
                if task is None or task.status in TERMINAL_STATUSES:
                    return
                budget = Deadline((task.deadline_at - datetime.now(UTC)).total_seconds())

            async def execute():
                async with self._semaphore:
                    budget.remaining()
                    await self.job(task_id, budget)

            await budget.run(execute)
        except asyncio.CancelledError:
            self._fail(task_id, "INTERRUPTED")
            raise
        except TaskDeadlineExceeded:
            self._fail(task_id, "TASK_TIMEOUT")
        except (ModelFailure, AppError) as error:
            self._fail(task_id, str(error.code))
        except SQLAlchemyError:
            self._fail(task_id, "SAVE_FAILED")
        except Exception:
            # Never log exception text: provider/DB exceptions may contain credentials or material.
            self._fail(task_id, "INTERNAL_ERROR")

    def _fail(self, task_id: UUID, code: str):
        try:
            with Session(self.engine) as db, db.begin():
                db.execute(
                    update(GenerationTask)
                    .where(
                        GenerationTask.id == task_id,
                        GenerationTask.status.not_in(TERMINAL_STATUSES),
                    )
                    .values(status="failed", error_code=code, finished_at=datetime.now(UTC))
                )
            self._pending_failures.pop(task_id, None)
        except SQLAlchemyError:
            self._pending_failures[task_id] = code
            logger.warning("Task failure persistence deferred; task_id=%s code=%s", task_id, code)

    async def _sweep(self):
        while True:
            await asyncio.sleep(2)
            try:
                # A lost session also loses the advisory lock. Stop instead of silently
                # continuing alongside another scheduler after database recovery.
                self._lock_connection.execute(text("SELECT 1"))
                for task_id, code in list(self._pending_failures.items()):
                    self._fail(task_id, code)
                with Session(self.engine) as db:
                    expired = list(
                        db.scalars(
                            select(GenerationTask.id).where(
                                GenerationTask.status.not_in(TERMINAL_STATUSES),
                                GenerationTask.deadline_at <= datetime.now(UTC),
                            )
                        )
                    )
                for task_id in expired:
                    self._fail(task_id, "TASK_TIMEOUT")
                    if task_id in self._jobs:
                        self._jobs[task_id].cancel()
            except SQLAlchemyError:
                self.ready = False
                for task in list(self._jobs.values()):
                    task.cancel()
                logger.warning("Scheduler database session lost; restart required")
                return

    def _release_lock(self):
        if self._lock_connection is not None:
            try:
                self._lock_connection.execute(text("SELECT pg_advisory_unlock(724905182)"))
            except SQLAlchemyError:
                pass  # The server releases session locks when the connection is lost.
            finally:
                self._lock_connection.close()
                self._lock_connection = None

    async def close(self):
        self.ready = False
        jobs = list(self._jobs.values())
        for task in jobs:
            task.cancel()
        if self._monitor:
            self._monitor.cancel()
            jobs.append(self._monitor)
        await asyncio.gather(*jobs, return_exceptions=True)
        for task_id, code in list(self._pending_failures.items()):
            self._fail(task_id, code)
        self._release_lock()
