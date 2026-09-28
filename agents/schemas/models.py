"""Provider-neutral contracts. Credentials never belong in workflow snapshots."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from agents.schemas.resources import ContractModel

NonBlank = Annotated[str, StringConstraints(strict=True, min_length=1)]


class ModelProtocol(StrEnum):
    CHAT_COMPLETIONS = "chat_completions"
    RESPONSES = "responses"
    MESSAGES = "messages"
    GEMINI = "gemini"


class FrozenContract(ContractModel):
    model_config = {**ContractModel.model_config, "frozen": True}


class ModelSelection(FrozenContract):
    configuration_id: NonBlank
    configuration_version: int = Field(strict=True, ge=1)
    protocol: ModelProtocol
    model_id: NonBlank


class ModelMessage(FrozenContract):
    role: Literal["system", "user", "assistant"]
    content: NonBlank = Field(repr=False)


class ModelRequest(FrozenContract):
    selection: ModelSelection
    messages: tuple[ModelMessage, ...] = Field(min_length=1, repr=False)


class ModelUsage(FrozenContract):
    # Unknown usage is different from zero usage. Providers may omit these fields.
    input_tokens: int | None = Field(default=None, strict=True, ge=0)
    output_tokens: int | None = Field(default=None, strict=True, ge=0)


class ModelResponse(FrozenContract):
    text: NonBlank = Field(repr=False)
    model_id: NonBlank
    usage: ModelUsage = Field(default_factory=ModelUsage)


class ModelErrorCode(StrEnum):
    AUTH = "MODEL_AUTH"
    NOT_FOUND = "MODEL_NOT_FOUND"
    RATE_LIMIT = "MODEL_RATE_LIMIT"
    TIMEOUT = "MODEL_TIMEOUT"
    TRANSPORT = "MODEL_TRANSPORT"
    UNAVAILABLE = "MODEL_UNAVAILABLE"
    FORMAT = "MODEL_FORMAT"
    UNSUPPORTED = "MODEL_UNSUPPORTED"


class ModelFailure(Exception):
    """Only a stable code is printable; never carry a response body, URL or key."""

    def __init__(self, code: ModelErrorCode, *, retry_after_seconds: float | None = None):
        import math

        if retry_after_seconds is not None and (
            not math.isfinite(retry_after_seconds) or retry_after_seconds < 0
        ):
            raise ValueError("Retry delay must be finite and non-negative")
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code.value)

    @property
    def retryable(self) -> bool:
        return self.code in {
            ModelErrorCode.RATE_LIMIT,
            ModelErrorCode.TIMEOUT,
            ModelErrorCode.TRANSPORT,
            ModelErrorCode.UNAVAILABLE,
        }
