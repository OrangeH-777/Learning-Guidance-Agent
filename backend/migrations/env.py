"""Alembic infrastructure; business tables and migrations are future work."""

from alembic import context

from backend.app.core.config import get_settings
from backend.app.db import models  # noqa: F401
from backend.app.db.base import Base
from backend.app.db.session import create_database_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = get_settings().database_url.get_secret_value()
    if not url:
        raise RuntimeError("Set DATABASE_URL before running migrations.")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(get_settings())
    if engine is None:
        raise RuntimeError("Set DATABASE_URL before running migrations.")
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
