"""A shared SQL predicate, applied BEFORE ranking and to source previews."""

from uuid import UUID

from sqlalchemy import select

from backend.app.db.models import KnowledgeChunk, KnowledgeDocument


def source_access(user_id: UUID):
    return ((KnowledgeDocument.visibility == "public") & KnowledgeDocument.owner_id.is_(None)) | (
        (KnowledgeDocument.visibility == "private") & (KnowledgeDocument.owner_id == user_id)
    )


def scoped_chunks(*, user_id: UUID, course_id: str, index_version: str):
    if not isinstance(user_id, UUID) or not course_id or not index_version:
        raise ValueError("Authenticated user, course and index version are required")
    return (
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument)
        .where(
            KnowledgeDocument.course_id == course_id,
            KnowledgeChunk.index_version == index_version,
            source_access(user_id),
        )
    )
