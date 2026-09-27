"""Create the database engine without connecting during application import."""

from sqlalchemy import Engine, create_engine

from backend.app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine | None:
    url = settings.database_url.get_secret_value()
    if not url:
        return None
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
