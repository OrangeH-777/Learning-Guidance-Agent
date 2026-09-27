"""Read-only database and pgvector availability check."""

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


def check_database(engine: Engine | None) -> dict[str, str]:
    if engine is None:
        return {"status": "not_configured", "database": "not_configured", "pgvector": "unknown"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            vector_version = connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
    except SQLAlchemyError:
        # Database errors can contain connection credentials; do not return their text.
        return {"status": "unavailable", "database": "unavailable", "pgvector": "unknown"}
    return {
        "status": "ok" if vector_version else "not_ready",
        "database": "ok",
        "pgvector": "ok" if vector_version else "missing",
    }
