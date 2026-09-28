import hashlib
import re
import unicodedata
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.retrieval.catalog import read_course, read_source
from agents.retrieval.vector import Embedder
from backend.app.db.models import Course, KnowledgeChunk, KnowledgeDocument


def chunks(markdown: str, *, max_characters: int) -> list[tuple[str, str]]:
    if max_characters < 1:
        raise ValueError("Chunk size must be positive")
    normalized = unicodedata.normalize("NFC", markdown.replace("\r\n", "\n").replace("\r", "\n"))
    heading, buffer, result = "正文", "", []
    for paragraph in re.split(r"\n\s*\n", normalized):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if paragraph.startswith("#"):
            if buffer:
                result.append((heading, buffer))
                buffer = ""
            heading = paragraph.lstrip("# ").splitlines()[0]
        for offset in range(0, len(paragraph), max_characters):
            piece = paragraph[offset : offset + max_characters]
            if buffer and len(buffer) + len(piece) + 2 > max_characters:
                result.append((heading, buffer))
                buffer = ""
            buffer = buffer + "\n\n" + piece if buffer else piece
    if buffer:
        result.append((heading, buffer))
    return result


async def index_course(
    engine,
    directory: Path,
    embedder: Embedder,
    *,
    index_version: str,
    chunk_characters: int = 1200,
    allow_unreviewed: bool = False,
):
    manifest = read_course(directory)
    if not manifest.sources:
        raise ValueError("A course without source documents cannot become ready")
    if not allow_unreviewed and any(s.review_status != "approved" for s in manifest.sources):
        raise ValueError(
            "Sources require content review; use explicit preview mode only for development"
        )
    # Changed source metadata/content must never silently reuse an existing index.
    prepared = [(source, read_source(directory, source)) for source in manifest.sources]
    material_digest = hashlib.sha256(
        (
            manifest.model_dump_json()
            + "".join(content for _, content in prepared)
            + embedder.model_id
            + str(embedder.dimensions)
            + str(chunk_characters)
        ).encode()
    ).hexdigest()
    marker = material_digest
    with Session(engine) as db:
        course = db.get(Course, manifest.id)
        if course is None:
            raise ValueError("Import the course catalog before indexing")
        old = db.execute(
            select(
                KnowledgeDocument.version, KnowledgeChunk.embedding_model, KnowledgeChunk.dimensions
            )
            .join(KnowledgeChunk)
            .where(
                KnowledgeDocument.course_id == manifest.id,
                KnowledgeChunk.index_version == index_version,
            )
        ).all()
        if old:
            if all(
                v == marker and m == embedder.model_id and d == embedder.dimensions
                for v, m, d in old
            ):
                course.active_index_version = index_version
                db.commit()
                return {"status": "unchanged", "chunks": len(old)}
            raise ValueError(
                "Index version already belongs to other content/model; choose a new version"
            )
    # No write transaction spans external calls; failures leave the old index active.
    compiled = []
    for source, content in prepared:
        pieces = chunks(content, max_characters=chunk_characters)
        vectors = await embedder.embed([body for _, body in pieces], timeout_seconds=60)
        if len(vectors) != len(pieces):
            raise ValueError("Embedding result count mismatch")
        compiled.append((source, content, pieces, vectors))
    with Session(engine) as db, db.begin():
        db.execute(select(func.pg_advisory_xact_lock(724905183)))
        course = db.get(Course, manifest.id)
        if course.content_version != manifest.version:
            raise ValueError("Course changed during indexing")
        # Another builder may have committed while this one was calling the embedder.
        committed = db.execute(
            select(
                KnowledgeDocument.version, KnowledgeChunk.embedding_model, KnowledgeChunk.dimensions
            )
            .join(KnowledgeChunk)
            .where(
                KnowledgeDocument.course_id == manifest.id,
                KnowledgeChunk.index_version == index_version,
            )
        ).all()
        if committed:
            if not all(
                v == marker and m == embedder.model_id and d == embedder.dimensions
                for v, m, d in committed
            ):
                raise ValueError("Index version was claimed by another build")
            course.active_index_version = index_version
            return {"status": "unchanged", "chunks": len(committed)}
        for source, content, pieces, vectors in compiled:
            digest = hashlib.sha256(content.encode()).hexdigest()
            document = db.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.course_id == manifest.id,
                    KnowledgeDocument.source_key == source.id,
                    KnowledgeDocument.version == marker,
                )
            )
            if document is None:
                document = KnowledgeDocument(
                    course_id=manifest.id,
                    owner_id=None,
                    visibility="public",
                    source_key=source.id,
                    title=source.title,
                    locator=source.source_url,
                    license=source.license,
                    content_hash=digest,
                    version=marker,
                )
                db.add(document)
                db.flush()
            for ordinal, ((locator, body), vector) in enumerate(zip(pieces, vectors, strict=True)):
                existing = db.scalar(
                    select(KnowledgeChunk.id).where(
                        KnowledgeChunk.document_id == document.id,
                        KnowledgeChunk.ordinal == ordinal,
                        KnowledgeChunk.index_version == index_version,
                    )
                )
                if existing is None:
                    db.add(
                        KnowledgeChunk(
                            document_id=document.id,
                            ordinal=ordinal,
                            locator=f"{source.section} / {locator}",
                            content=body,
                            index_version=index_version,
                            embedding_model=embedder.model_id,
                            dimensions=embedder.dimensions,
                            embedding=vector,
                        )
                    )
        course.active_index_version = index_version
    return {"status": "indexed", "chunks": sum(len(pieces) for _, _, pieces, _ in compiled)}
