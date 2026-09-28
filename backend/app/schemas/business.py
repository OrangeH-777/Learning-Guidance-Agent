from typing import Annotated, Literal

from pydantic import Field, SecretStr, StringConstraints, field_validator

from agents.schemas.models import ModelProtocol
from backend.app.schemas.inputs import InputModel, ProfileFields, RequestKey, TopicText

CourseId = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]{0,63}$")]


class ProfileConfirmation(ProfileFields):
    expected_version: int = Field(strict=True, ge=0)


class ModelConfigurationInput(InputModel):
    expected_version: int = Field(strict=True, ge=0)
    protocol: ModelProtocol
    base_url: str = Field(min_length=1, max_length=2048)
    model_id: str = Field(min_length=1, max_length=200)
    api_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("model_id")
    @classmethod
    def model_name(cls, value: str) -> str:
        if value != value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid model identifier")
        return value


class TaskCreate(InputModel):
    course_id: CourseId
    topic: TopicText
    resource_type: Literal["lecture", "exercise", "mindmap"]
    profile_version: int = Field(strict=True, ge=1)
    model_version: int = Field(strict=True, ge=1)
    request_key: RequestKey

    @field_validator("topic", "request_key")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value cannot be blank")
        return value


class TaskRetry(InputModel):
    request_key: RequestKey
