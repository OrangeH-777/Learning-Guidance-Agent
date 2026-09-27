"""Run from the repository root: uv run uvicorn backend.app.main:app --reload."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.router import router as api_router
from backend.app.api.routes.health import router as health_router
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import create_database_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_database_engine(settings if settings is not None else get_settings())
        application.state.database_engine = engine
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    application = FastAPI(
        title="Learning Guidance Agent",
        version="0.1.0",
        description="Infrastructure scaffold; business features are not implemented.",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()
