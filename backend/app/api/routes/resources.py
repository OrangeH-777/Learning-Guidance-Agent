from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.retrieval.access import source_access
from backend.app.api.dependencies import current_user, database
from backend.app.core.errors import AppError
from backend.app.db.models import GenerationTask, KnowledgeChunk, KnowledgeDocument, Resource, User
from backend.app.schemas.responses import HistoryResponse, ResourceResponse, SourceResponse

router = APIRouter(tags=["resources"])


def visible_source(user_id):
    return source_access(user_id)


@router.get("/resources", response_model=HistoryResponse)
def history(
    user: User = Depends(current_user),
    db: Session = Depends(database),
    course_id: str | None = None,
    topic: str = Query(default="", max_length=100),
    resource_type: Literal["lecture", "exercise", "mindmap"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
):
    query = select(Resource).where(Resource.user_id == user.id)
    if course_id:
        query = query.where(Resource.course_id == course_id)
    if topic:
        query = query.where(Resource.topic.contains(topic, autoescape=True))
    if resource_type:
        query = query.where(Resource.resource_type == resource_type)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Resource.created_at.desc(), Resource.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {
                "id": r.id,
                "title": r.content["title"],
                "course_id": r.course_id,
                "topic": r.topic,
                "resource_type": r.resource_type,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "filters": {"course_id": course_id, "topic": topic, "resource_type": resource_type},
    }


@router.get("/resources/{resource_id}", response_model=ResourceResponse)
def resource(
    resource_id: UUID, user: User = Depends(current_user), db: Session = Depends(database)
):
    row = db.scalar(select(Resource).where(Resource.id == resource_id, Resource.user_id == user.id))
    if row is None:
        raise AppError(404, "NOT_FOUND", "资源不存在")
    return {
        "id": row.id,
        "task_id": row.task_id,
        "course_id": row.course_id,
        "topic": row.topic,
        "content": row.content,
        "metadata": row.metadata_snapshot,
        "created_at": row.created_at,
        "human_pass": row.human_pass,
        "notice": "由AI生成，仅供参考",
    }


@router.get("/courses/{course_id}/sources/{source_id}", response_model=SourceResponse)
def source(
    course_id: str,
    source_id: UUID,
    user: User = Depends(current_user),
    db: Session = Depends(database),
):
    task = db.scalar(
        select(GenerationTask)
        .where(
            GenerationTask.knowledge_version == str(source_id),
            GenerationTask.course_id == course_id,
            GenerationTask.user_id == user.id,
        )
        .limit(1)
    )
    if task and task.chapter_snapshot:
        chapter = task.chapter_snapshot
        return dict(
            id=source_id,
            title=chapter["title"],
            locator=chapter["title"],
            source=chapter["source"],
            license=chapter["license"],
            content=chapter["content"],
            version=chapter["version"],
            index_version=str(source_id),
        )
    row = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument)
        .where(
            KnowledgeChunk.id == source_id,
            KnowledgeDocument.course_id == course_id,
            visible_source(user.id),
        )
    ).first()
    if not row:
        raise AppError(404, "NOT_FOUND", "来源不存在")
    chunk, document = row
    return {
        "id": chunk.id,
        "title": document.title,
        "locator": chunk.locator,
        "source": document.locator,
        "license": document.license,
        "content": chunk.content,
        "version": document.version,
        "index_version": chunk.index_version,
    }
