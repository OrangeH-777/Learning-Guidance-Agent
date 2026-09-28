import os
import subprocess
import sys

import pytest
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.db.base import Base
from backend.app.db.models import Course
from backend.app.main import create_app
from scripts.test_database import require_test_database


@pytest.fixture(scope="session")
def test_engine():
    local = dotenv_values(PROJECT_ROOT / ".env")
    url = os.environ.get("TEST_DATABASE_URL") or local.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for real PostgreSQL tests")
    production = os.environ.get("DATABASE_URL") or local.get("DATABASE_URL")
    try:
        url = require_test_database(url, production)
    except ValueError as error:
        pytest.fail(str(error))
    environment = {**os.environ, "DATABASE_URL": url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
    )
    if result.returncode:
        pytest.fail("Test database migration failed; run migration checks separately")
    engine = create_engine(url, hide_parameters=True)
    yield engine
    engine.dispose()


@pytest.fixture
def app(test_engine):
    names = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
    with test_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {names} CASCADE"))
    with Session(test_engine) as db:
        db.add_all(
            [
                Course(
                    id=name,
                    name=name,
                    description="test only",
                    enabled=True,
                    content_version="fixture-v1",
                )
                for name in ("data_structure", "test_course")
            ]
        )
        db.commit()
    settings = Settings(
        _env_file=None,
        database_url=SecretStr(test_engine.url.render_as_string(hide_password=False)),
        model_credential_encryption_key=SecretStr(Fernet.generate_key().decode()),
    )
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def register(client, username="learner_a"):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Study2026", "password_confirmation": "Study2026"},
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()
