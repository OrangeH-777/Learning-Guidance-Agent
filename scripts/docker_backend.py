"""Start the standalone backend container with its mounted local settings and textbooks."""

import json
import os
import sys
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from backend.app.core.config import Settings, get_settings
from backend.app.db.session import create_database_engine
from scripts import bootstrap_admin, import_courses


def main():
    local = Settings()
    if not local.database_url.get_secret_value():
        raise SystemExit("Mount the project .env at /app/.env before starting this container.")
    database = make_url(local.database_url.get_secret_value()).set(
        host="lga-postgres-dev", port=5432
    )
    os.environ["DATABASE_URL"] = database.render_as_string(hide_password=False)
    os.environ["ALLOWED_ORIGINS"] = json.dumps(
        [f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (8088, 8008)]
    )
    os.environ["PUBLIC_KNOWLEDGE_DIR"] = "/app/knowledge"
    os.environ["OPENAI_PROXY_HOST"] = "host.docker.internal"
    settings = get_settings()
    engine = create_database_engine(settings)
    try:
        for attempt in range(45):
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                break
            except OperationalError:
                if attempt == 44:
                    raise SystemExit(
                        "Database unavailable. Check lga-postgres-dev and the Docker network."
                    ) from None
                time.sleep(2)
    finally:
        engine.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    import_courses.main()
    if settings.admin_username or settings.admin_password.get_secret_value():
        bootstrap_admin.main()
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
    )


if __name__ == "__main__":
    main()
