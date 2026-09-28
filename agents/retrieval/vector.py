"""Exact pgvector search, with authorization and version filters inside the query."""

import math
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from agents.retrieval.access import scoped_chunks
from agents.schemas.workflow import SourceFragment
from backend.app.db.models import KnowledgeChunk


class Embedder(Protocol):
    model_id: str
    dimensions: int

    async def embed(self, texts: list[str], *, timeout_seconds: float) -> list[list[float]]: ...


def validate_vector(values: list[float], dimensions: int) -> list[float]:
    if len(values) != dimensions or dimensions < 1:
        raise ValueError("Embedding dimensions do not match the configured index")
    if any(
        isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
        for v in values
    ):
        raise ValueError("Embedding must contain finite numbers")
    if not any(values):
        raise ValueError("Zero embeddings cannot be used for cosine retrieval")
    return values


def search(
    db: Session,
    *,
    user_id: UUID,
    course_id: str,
    index_version: str,
    model_id: str,
    vector: list[float],
    dimensions: int,
    limit: int,
    max_cosine_distance: float,
) -> tuple[SourceFragment, ...]:
    validate_vector(vector, dimensions)
    if not 1 <= limit <= 50 or not 0 <= max_cosine_distance <= 2:
        raise ValueError("Invalid retrieval parameters")
    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    query = (
        scoped_chunks(user_id=user_id, course_id=course_id, index_version=index_version)
        .where(
            KnowledgeChunk.embedding_model == model_id,
            KnowledgeChunk.dimensions == dimensions,
            distance <= max_cosine_distance,
        )
        .order_by(distance, KnowledgeChunk.id)
        .limit(limit)
    )
    return tuple(
        SourceFragment(
            id=chunk.id,
            course_id=document.course_id,
            visibility=document.visibility,
            owner_id=document.owner_id,
            content=chunk.content,
            locator=chunk.locator,
            index_version=chunk.index_version,
        )
        for chunk, document in db.execute(query)
    )


class KeywordRetriever(Protocol):
    """Reserved interface; no unreviewed Chinese tokenizer or hybrid ranking is enabled."""

    async def search(
        self, *, user_id: UUID, course_id: str, index_version: str, query: str, limit: int
    ) -> tuple[SourceFragment, ...]: ...
