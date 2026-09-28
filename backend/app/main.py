"""Run from the repository root: uv run uvicorn backend.app.main:app --reload."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api.router import router as api_router
from backend.app.api.routes.health import router as health_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import register_error_handlers
from backend.app.db.session import create_database_engine
from backend.app.services.generation import generate_resource
from backend.app.services.knowledge import embedder_for
from backend.app.services.public_knowledge import PublicKnowledgeManager
from backend.app.tasks.executor import TaskExecutor


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        resolved_settings = settings if settings is not None else get_settings()
        application.state.settings = resolved_settings
        engine = create_database_engine(resolved_settings)
        application.state.database_engine = engine
        application.state.public_knowledge = PublicKnowledgeManager(
            engine, resolved_settings, lambda config: application.state.embedder_factory(config)
        )
        executor = None
        if engine is not None:
            from sqlalchemy.exc import SQLAlchemyError

            executor = TaskExecutor(
                engine,
                resolved_settings,
                lambda task_id, budget: generate_resource(application, task_id, budget),
            )
            try:
                executor.start()
            except SQLAlchemyError:
                # Liveness is independent of database availability; business routes return 503.
                executor = None
        application.state.executor = executor
        try:
            yield
        finally:
            await application.state.public_knowledge.close()
            if executor is not None:
                await executor.close()
            if engine is not None:
                engine.dispose()

    application = FastAPI(
        title="Learning Guidance Agent",
        version="0.1.0",
        description="Personal learning profiles, course knowledge and verified learning resources.",
        lifespan=lifespan,
    )
    application.include_router(health_router)
    application.include_router(api_router)

    @application.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    register_error_handlers(application)
    from backend.app.services.models import provider_for

    application.state.provider_factory = provider_for
    application.state.embedder_factory = embedder_for
    return application


app = create_app()
