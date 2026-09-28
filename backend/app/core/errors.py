"""Stable client errors without echoing request bodies, secrets or provider failures."""

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_FAILED = "AUTH_FAILED"
    NOT_FOUND = "NOT_FOUND"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    INVALID_INPUT = "INVALID_INPUT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    BUSY = "BUSY"
    MODEL_RATE_LIMIT = "MODEL_RATE_LIMIT"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    MODEL_FORMAT = "MODEL_FORMAT"
    CONTENT_REJECTED = "CONTENT_REJECTED"
    SAVE_FAILED = "SAVE_FAILED"
    INTERRUPTED = "INTERRUPTED"


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


def register_error_handlers(app: FastAPI) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    from agents.schemas.models import ModelFailure

    @app.exception_handler(ResponseValidationError)
    async def handle_invalid_response(request: Request, error: ResponseValidationError):
        # Validation errors may contain an entire private database result. Never echo or log it.
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "服务响应异常，请稍后重试"}},
        )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status,
            content={"error": {"code": error.code, "message": error.message}},
        )

    @app.exception_handler(ModelFailure)
    async def handle_model_error(request: Request, error: ModelFailure) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "error": {"code": error.code, "message": "模型调用失败，请检查配置或稍后重试"}
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "DATABASE_UNAVAILABLE", "message": "数据服务暂时不可用"}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_invalid_input(request: Request, error: RequestValidationError) -> JSONResponse:
        del request
        # Pydantic's default messages/context/input can contain user-controlled text.
        # Keep only model field paths and a generic message; omit attacker-supplied extra keys.
        fields = [
            {
                "field": ".".join(str(part) for part in item["loc"]),
                "message": "字段缺失、类型不符或超出允许范围",
            }
            for item in error.errors()
            if item["type"] not in {"extra_forbidden", "json_invalid"}
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": ErrorCode.INVALID_INPUT,
                    "message": "输入无效，请检查字段内容",
                    "fields": fields,
                }
            },
        )
