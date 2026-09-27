"""Stable client errors without echoing request bodies, secrets or provider failures."""

from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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


def register_error_handlers(app: FastAPI) -> None:
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
