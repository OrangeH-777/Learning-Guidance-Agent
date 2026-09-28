"""Explicit browser-test server, isolated *_test DB and test-only model factories."""

import os
import subprocess
import sys

import uvicorn
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.db.base import Base
from backend.app.db.models import Course, KnowledgeChunk, KnowledgeDocument
from backend.app.main import create_app
from scripts.test_database import require_test_database
from tests.integration.test_generation_flow import FakeEmbedder, FakeProvider


def main():
    values = dotenv_values(PROJECT_ROOT / ".env")
    url = os.environ.get("TEST_DATABASE_URL") or values.get("TEST_DATABASE_URL")
    try:
        url = require_test_database(
            url, os.environ.get("DATABASE_URL") or values.get("DATABASE_URL")
        )
    except ValueError as error:
        raise SystemExit(str(error)) from None
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit("Test database migration failed")
    engine = create_engine(url, hide_parameters=True)
    with engine.begin() as connection:
        names = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {names} CASCADE"))
    with Session(engine) as db:
        db.add(
            Course(
                id="test_course",
                name="隔离测试课程",
                description="TEST ONLY",
                enabled=True,
                content_version="fixture",
            )
        )
        db.add(
            Course(
                id="data_structure",
                name="数据结构（浏览器测试）",
                description="TEST ONLY",
                enabled=True,
                content_version="fixture",
                active_index_version="fixture-index",
            )
        )
        db.flush()
        document = KnowledgeDocument(
            course_id="data_structure",
            visibility="public",
            owner_id=None,
            source_key="fixture",
            title="测试来源",
            locator="fixture:stack",
            license="仅测试使用",
            content_hash="a" * 64,
            version="fixture",
        )
        db.add(document)
        db.flush()
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                ordinal=0,
                locator="fixture:stack",
                content="栈后进先出",
                index_version="fixture-index",
                embedding_model="test-embedding",
                dimensions=3,
                embedding=[1, 0, 0],
            )
        )
        db.commit()
    engine.dispose()
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(url),
        model_credential_encryption_key=SecretStr(Fernet.generate_key().decode()),
        embedding_index_version="fixture-index",
        allowed_origins=["http://127.0.0.1:5174"],
    )
    app = create_app(settings)
    app.state.provider_factory = lambda configuration, settings: FakeProvider()
    app.state.embedder_factory = lambda settings: FakeEmbedder()
    uvicorn.run(app, host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
