"""First-phase API paths and shared error contracts."""

from fastapi import APIRouter

from backend.app.api.routes import admin, auth, conversations, models, profiles, resources, tasks
from backend.app.schemas.responses import ErrorResponse

router = APIRouter(
    prefix="/api",
    responses={
        code: {"model": ErrorResponse}
        for code in (401, 403, 404, 409, 413, 422, 429, 500, 502, 503)
    },
)
router.include_router(auth.router)
router.include_router(models.router)
router.include_router(profiles.router)
router.include_router(tasks.router)
router.include_router(resources.router)
router.include_router(conversations.router)
router.include_router(admin.router)
