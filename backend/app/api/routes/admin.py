from fastapi import APIRouter, Depends, Query, Request
from starlette.concurrency import run_in_threadpool

from backend.app.api.dependencies import current_admin
from backend.app.core.errors import AppError
from backend.app.schemas.materials import (
    AdminCourse,
    CourseCreate,
    MaterialDetail,
    MaterialPreview,
    MaterialSave,
    MaterialSaved,
)
from backend.app.services.material_text import MAX_FILE_BYTES, MaterialError, preview_document

router = APIRouter(
    prefix="/admin", tags=["public knowledge"], dependencies=[Depends(current_admin)]
)


@router.get("/courses", response_model=list[AdminCourse])
def courses(request: Request):
    return request.app.state.public_knowledge.courses()


@router.post("/courses", response_model=AdminCourse, status_code=201)
async def create_course(payload: CourseCreate, request: Request, admin=Depends(current_admin)):
    manager = request.app.state.public_knowledge
    async with manager.lock:
        return await run_in_threadpool(manager.create_course, payload, admin.username)


@router.get("/courses/{course_id}/materials/{source_id}", response_model=MaterialDetail)
def material(course_id: str, source_id: str, request: Request):
    return request.app.state.public_knowledge.detail(course_id, source_id)


@router.post(
    "/materials/preview",
    response_model=MaterialPreview,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def preview(request: Request, filename: str = Query(min_length=1, max_length=255)):
    manager = request.app.state.public_knowledge
    if manager.preview_lock.locked():
        raise AppError(429, "BUSY", "正在提取另一份教材，请稍后重试")
    async with manager.preview_lock:
        content = bytearray()
        async for part in request.stream():
            if len(content) + len(part) > MAX_FILE_BYTES:
                raise AppError(413, "FILE_TOO_LARGE", "单文件不能超过10 MB")
            content.extend(part)
        try:
            return await run_in_threadpool(preview_document, bytes(content), filename)
        except MaterialError as error:
            raise AppError(422, "MATERIAL_INVALID", str(error)) from None


@router.post("/courses/{course_id}/materials", response_model=MaterialSaved, status_code=201)
async def save(course_id: str, payload: MaterialSave, request: Request):
    manager = request.app.state.public_knowledge
    if manager.lock.locked():
        raise AppError(409, "KNOWLEDGE_BUSY", "教材正在保存，请稍后重试")
    async with manager.lock:
        return await run_in_threadpool(manager.save, course_id, payload)
