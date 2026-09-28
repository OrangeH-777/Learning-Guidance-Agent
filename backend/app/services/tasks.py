"""Task acceptance and state changes use short transactions, never model I/O."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.prompts.version import PROMPT_VERSION
from backend.app.api.routes.profiles import latest_profile, require_course
from backend.app.core.config import Settings
from backend.app.core.errors import AppError
from backend.app.db.models import GenerationTask, ModelConfiguration, Resource, User
from backend.app.schemas.business import TaskCreate
from backend.app.services.models import latest_model
from backend.app.tasks.state import TERMINAL_STATUSES, TaskProgress, TaskStatus


def task_public(task: GenerationTask, resource_id=None) -> dict:
    return {
        "id": str(task.id),
        "course_id": task.course_id,
        "topic": task.topic,
        "resource_type": task.resource_type,
        "status": task.status,
        "profile_version": task.profile_version,
        "created_at": task.created_at,
        "deadline_at": task.deadline_at,
        "finished_at": task.finished_at,
        "error_code": task.error_code,
        "parent_task_id": task.parent_task_id,
        "resource_id": resource_id,
        "content_regenerations": task.content_regenerations,
        "knowledge_version": task.knowledge_version,
        "prompt_version": task.prompt_version,
        "telemetry": task.telemetry or None,
    }


def owned_task(db: Session, user_id: UUID, task_id: UUID) -> GenerationTask:
    task = db.scalar(
        select(GenerationTask).where(
            GenerationTask.id == task_id, GenerationTask.user_id == user_id
        )
    )
    if task is None:
        raise AppError(404, "NOT_FOUND", "任务不存在")
    return task


def create_task(
    db: Session,
    user_id: UUID,
    payload: TaskCreate,
    settings: Settings,
    *,
    parent: GenerationTask | None = None,
) -> GenerationTask:
    parameters = payload.model_dump(exclude={"request_key"})
    if parent:
        parameters["parent_task_id"] = str(parent.id)
    digest = hashlib.sha256(
        json.dumps(parameters, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    # Same-user operations share a row lock; global capacity uses a PG advisory lock.
    db.scalar(select(User).where(User.id == user_id).with_for_update())
    existing = db.scalar(
        select(GenerationTask).where(
            GenerationTask.user_id == user_id, GenerationTask.request_key == payload.request_key
        )
    )
    if existing:
        if existing.request_digest != digest:
            raise AppError(409, "IDEMPOTENCY_CONFLICT", "该请求标识已用于不同参数")
        return existing
    course = require_course(db, payload.course_id)
    if not course.active_index_version:
        raise AppError(409, "KNOWLEDGE_NOT_READY", "课程知识索引尚未就绪")
    profile = latest_profile(db, user_id, payload.course_id)
    model = latest_model(db, user_id)
    if parent is None:
        if not profile or profile.version != payload.profile_version:
            raise AppError(409, "VERSION_CONFLICT", "请确认当前课程的最新画像")
        if not model or model.retired or model.version != payload.model_version:
            raise AppError(409, "VERSION_CONFLICT", "模型设置已变化，请重新确认")
        snapshot = profile.fields
    else:
        model = db.get(ModelConfiguration, parent.model_configuration_id)
        snapshot = parent.profile_snapshot
    if not model or not model.tested_at:
        raise AppError(409, "MODEL_NOT_TESTED", "请先在模型设置中完成连接测试")
    # An unspecified queue means no waiting slots: never invent an unmeasured queue capacity.
    capacity = settings.global_generation_limit + (settings.task_queue_capacity or 0)
    db.execute(select(func.pg_advisory_xact_lock(724905181)))
    active = select(GenerationTask).where(GenerationTask.status.not_in(TERMINAL_STATUSES))
    if db.scalar(select(func.count()).select_from(active.subquery())) >= capacity:
        raise AppError(429, "BUSY", "生成服务繁忙，请稍后重试")
    if db.scalar(active.where(GenerationTask.user_id == user_id).limit(1)):
        raise AppError(409, "BUSY", "你已有进行中的任务")
    accepted = datetime.now(UTC)
    task = GenerationTask(
        user_id=user_id,
        course_id=payload.course_id,
        request_key=payload.request_key,
        request_digest=digest,
        parent_task_id=parent.id if parent else None,
        topic=payload.topic,
        resource_type=payload.resource_type,
        profile_version=payload.profile_version,
        profile_snapshot=snapshot,
        model_configuration_id=model.id,
        knowledge_version=parent.knowledge_version if parent else course.active_index_version,
        prompt_version=parent.prompt_version if parent else PROMPT_VERSION,
        created_at=accepted,
        deadline_at=accepted + timedelta(seconds=settings.task_timeout_seconds),
    )
    db.add(task)
    db.flush()
    return task


def advance_task(db: Session, task_id: UUID, target: TaskStatus, *, regeneration_limit: int = 2):
    task = db.scalar(select(GenerationTask).where(GenerationTask.id == task_id).with_for_update())
    if task is None:
        raise AppError(404, "NOT_FOUND", "任务不存在")
    if task.deadline_at <= datetime.now(UTC):
        from agents.workflows.runtime import TaskDeadlineExceeded

        raise TaskDeadlineExceeded()
    progress = TaskProgress(TaskStatus(task.status), task.content_regenerations).advance(
        target, regeneration_limit=regeneration_limit
    )
    task.status, task.content_regenerations = progress.status, progress.content_regenerations
    return task


def publish_resource(db: Session, task_id: UUID, content: dict, metadata: dict) -> UUID:
    """Caller owns commit; any failure rolls back BOTH resource and terminal status."""
    task = advance_task(db, task_id, TaskStatus.COMPLETED)
    resource = Resource(
        task_id=task.id,
        user_id=task.user_id,
        course_id=task.course_id,
        topic=task.topic,
        resource_type=task.resource_type,
        content=content,
        metadata_snapshot=metadata,
        source_ids=content["source_ids"],
        human_pass=False,
    )
    db.add(resource)
    task.finished_at = datetime.now(UTC)
    db.flush()
    if task.deadline_at <= datetime.now(UTC):
        from agents.workflows.runtime import TaskDeadlineExceeded

        raise TaskDeadlineExceeded()
    return resource.id
