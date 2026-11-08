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

    from agents.schemas.models import ModelErrorCode, ModelFailure

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

    model_hints = {
        ModelErrorCode.AUTH: "服务商拒绝访问，请核对完整 API Key、项目权限和服务可用范围",
        ModelErrorCode.NOT_FOUND: "服务商未找到接口或模型，请核对 Base URL、协议与模型 ID",
        ModelErrorCode.QUOTA: "服务商报告额度不足或支出已达上限，请检查组织余额和项目限额",
        ModelErrorCode.THROTTLED: "请求或令牌速率已达上限，请稍后重试并降低调用频率",
        ModelErrorCode.RATE_LIMIT: "服务商限制调用，请检查项目额度、余额和请求频率",
        ModelErrorCode.TIMEOUT: "连接或响应超时，请检查后端到模型服务的直连网络",
        ModelErrorCode.TRANSPORT: "网络连接失败，请检查后端 DNS、TLS 和直连网络",
        ModelErrorCode.UNAVAILABLE: "模型服务暂不可用，请稍后重试",
        ModelErrorCode.FORMAT: "响应格式不符合所选协议，请确认接口类型",
        ModelErrorCode.UNSUPPORTED: "地址不符合访问规则或服务商拒绝请求，请核对协议和服务地址",
    }

    @app.exception_handler(ModelFailure)
    async def handle_model_error(request: Request, error: ModelFailure) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "code": error.code,
                    "message": f"{model_hints[error.code]}（{error.code}）",
                }
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
