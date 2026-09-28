from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.dependencies import current_user, database
from backend.app.core.errors import AppError
from backend.app.db.models import GenerationTask, ModelConfiguration, Resource, User
from backend.app.schemas.business import TaskCreate, TaskRetry
from backend.app.schemas.responses import TaskResponse
from backend.app.services.tasks import create_task, owned_task, task_public

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=202, response_model=TaskResponse)
async def submit(
    payload: TaskCreate,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(database),
):
    if request.app.state.executor is None or not request.app.state.executor.ready:
        raise AppError(503, "NOT_READY", "任务执行器尚未就绪")
    task = create_task(db, user.id, payload, request.app.state.settings)
    db.commit()
    if task.status == "queued":
        request.app.state.executor.submit(task.id)
    return task_public(task)


@router.get("", response_model=list[TaskResponse])
def recent(
    user: User = Depends(current_user),
    db: Session = Depends(database),
    limit: int = Query(default=10, ge=1, le=50),
):
    rows = db.execute(
        select(GenerationTask, Resource.id)
        .outerjoin(Resource, Resource.task_id == GenerationTask.id)
        .where(GenerationTask.user_id == user.id)
        .order_by(GenerationTask.created_at.desc(), GenerationTask.id.desc())
        .limit(limit)
    )
    return [task_public(t, r) for t, r in rows]


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: UUID, user: User = Depends(current_user), db: Session = Depends(database)):
    task = owned_task(db, user.id, task_id)
    resource_id = db.scalar(
        select(Resource.id).where(Resource.task_id == task.id, Resource.user_id == user.id)
    )
    return task_public(task, resource_id)


@router.post("/{task_id}/retry", status_code=202, response_model=TaskResponse)
async def retry(
    task_id: UUID,
    payload: TaskRetry,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(database),
):
    if request.app.state.executor is None or not request.app.state.executor.ready:
        raise AppError(503, "NOT_READY", "任务执行器尚未就绪")
    parent = owned_task(db, user.id, task_id)
    if parent.status != "failed":
        raise AppError(409, "INVALID_STATE", "只有失败任务可以重试")
    model = db.get(ModelConfiguration, parent.model_configuration_id)
    task = create_task(
        db,
        user.id,
        TaskCreate(
            course_id=parent.course_id,
            topic=parent.topic,
            resource_type=parent.resource_type,
            profile_version=parent.profile_version,
            model_version=model.version,
            request_key=payload.request_key,
        ),
        request.app.state.settings,
        parent=parent,
    )
    db.commit()
    if task.status == "queued":
        request.app.state.executor.submit(task.id)
    return task_public(task)
