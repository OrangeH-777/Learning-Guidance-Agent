import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.retrieval.catalog import read_course
from agents.retrieval.indexing import chunks, index_course
from agents.retrieval.vector import search
from backend.app.core.config import PROJECT_ROOT
from backend.app.db.models import Course, KnowledgeChunk, KnowledgeDocument, User
from tests.integration.test_generation_flow import FakeEmbedder


async def test_repeat_index_and_new_model_version_preserve_old_sources(app, test_engine):
    with Session(test_engine) as db:
        course = db.get(Course, "data_structure")
        course.content_version = read_course(PROJECT_ROOT / "knowledge/data_structure").version
        db.commit()
    directory = PROJECT_ROOT / "knowledge/data_structure"
    with pytest.raises(ValueError, match="review"):
        await index_course(test_engine, directory, FakeEmbedder(), index_version="test-index")
    first = await index_course(
        test_engine, directory, FakeEmbedder(), index_version="test-index", allow_unreviewed=True
    )
    repeated = await index_course(
        test_engine, directory, FakeEmbedder(), index_version="test-index", allow_unreviewed=True
    )
    assert first["chunks"] == repeated["chunks"] > 0 and repeated["status"] == "unchanged"
    other = FakeEmbedder()
    other.model_id = "other-embedding"
    with pytest.raises(ValueError, match="version"):
        await index_course(
            test_engine, directory, other, index_version="test-index", allow_unreviewed=True
        )
    await index_course(
        test_engine, directory, other, index_version="test-index-2", allow_unreviewed=True
    )
    with Session(test_engine) as db:
        assert db.scalar(select(func.count()).select_from(KnowledgeChunk)) == 2 * first["chunks"]
        assert db.get(Course, "data_structure").active_index_version == "test-index-2"
        assert db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.index_version == "test-index"))


def test_vector_query_enforces_user_course_and_index_before_ranking(app, test_engine):
    with Session(test_engine) as db:
        a, b = (
            User(username="owner_a", password_hash="fixture"),
            User(username="owner_b", password_hash="fixture"),
        )
        db.add_all([a, b])
        db.flush()
        for i, (course, owner, visibility, version) in enumerate(
            [
                ("data_structure", None, "public", "v1"),
                ("data_structure", a.id, "private", "v1"),
                ("data_structure", b.id, "private", "v1"),
                ("test_course", None, "public", "v1"),
                ("data_structure", None, "public", "v2"),
            ]
        ):
            doc = KnowledgeDocument(
                course_id=course,
                owner_id=owner,
                visibility=visibility,
                source_key=f"source_{i}",
                title=f"source_{i}",
                locator="fixture",
                license="fixture",
                content_hash="a" * 64,
                version="fixture",
            )
            db.add(doc)
            db.flush()
            db.add(
                KnowledgeChunk(
                    document_id=doc.id,
                    ordinal=0,
                    locator="fixture",
                    content=str(i),
                    index_version=version,
                    embedding_model="fixture",
                    dimensions=3,
                    embedding=[1, 0, 0],
                )
            )
        db.commit()
        rows = search(
            db,
            user_id=a.id,
            course_id="data_structure",
            index_version="v1",
            model_id="fixture",
            vector=[1, 0, 0],
            dimensions=3,
            limit=10,
            max_cosine_distance=0.1,
        )
        assert {row.content for row in rows} == {"0", "1"}
        assert (
            search(
                db,
                user_id=a.id,
                course_id="data_structure",
                index_version="v1",
                model_id="fixture",
                vector=[0, 1, 0],
                dimensions=3,
                limit=10,
                max_cosine_distance=0.1,
            )
            == ()
        )


def test_chunk_boundaries_and_unicode_normalization():
    result = chunks("# Topic\r\n\r\n" + "e\u0301" * 100, max_characters=25)
    assert all(len(body) <= 25 and "\r" not in body for _, body in result)
    assert all(locator == "Topic" for locator, _ in result)
    assert "é" in result[1][1]


async def test_concurrent_builders_cannot_mix_models_under_one_index_version(app, test_engine):
    import asyncio

    with Session(test_engine) as db, db.begin():
        db.get(Course, "data_structure").content_version = read_course(
            PROJECT_ROOT / "knowledge/data_structure"
        ).version

    class RacingEmbedder(FakeEmbedder):
        async def embed(self, texts, *, timeout_seconds):
            await asyncio.sleep(0)
            return await super().embed(texts, timeout_seconds=timeout_seconds)

    a, b = RacingEmbedder(), RacingEmbedder()
    b.model_id = "other-model"
    results = await asyncio.gather(
        *[
            index_course(
                test_engine,
                PROJECT_ROOT / "knowledge/data_structure",
                model,
                index_version="race-v1",
                allow_unreviewed=True,
            )
            for model in (a, b)
        ],
        return_exceptions=True,
    )
    assert sum(isinstance(result, ValueError) for result in results) == 1
    with Session(test_engine) as db:
        models = set(
            db.scalars(
                select(KnowledgeChunk.embedding_model).where(
                    KnowledgeChunk.index_version == "race-v1"
                )
            )
        )
        assert len(models) == 1
