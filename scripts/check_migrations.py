"""Destructive migration round-trip in an explicitly isolated *_test database only."""

import json
import os
import subprocess
import sys

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.app.core.config import PROJECT_ROOT
from backend.app.db import models  # noqa: F401
from backend.app.db.base import Base
from scripts.test_database import require_test_database


def main():
    local = dotenv_values(PROJECT_ROOT / ".env")
    url = os.environ.get("TEST_DATABASE_URL") or local.get("TEST_DATABASE_URL")
    try:
        url = require_test_database(
            url, os.environ.get("DATABASE_URL") or local.get("DATABASE_URL")
        )
    except ValueError as error:
        raise SystemExit(str(error)) from None
    environment = {**os.environ, "DATABASE_URL": url}

    def alembic(*args):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            env=environment,
            cwd=PROJECT_ROOT,
            capture_output=True,
        )
        if result.returncode:
            raise SystemExit("Migration verification failed; no credentials displayed")

    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            names = ", ".join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
            connection.execute(text(f"TRUNCATE {names} CASCADE"))
        alembic("downgrade", "base")
        alembic("upgrade", "f645e3858478")
        alembic("upgrade", "head")
        alembic("check")
        alembic("downgrade", "f645e3858478")
        alembic("upgrade", "head")
        print(
            json.dumps(
                {
                    "database": make_url(url).database,
                    "empty_upgrade": "passed",
                    "revision_upgrade": "passed",
                    "empty_data_downgrade": "passed",
                    "metadata_diff": "none",
                }
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
