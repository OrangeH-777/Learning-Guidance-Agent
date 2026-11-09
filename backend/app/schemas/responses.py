"""Public response contracts; persistence entities and secrets never cross this boundary."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from agents.schemas.models import ModelProtocol, ModelSelection, ModelUsage
from agents.schemas.resources import ResourceDraft
from agents.schemas.workflow import ProfileSnapshot
from backend.app.schemas.inputs import ProfileFields, ProfileText
from backend.app.tasks.state import TaskStatus

ResourceType = Literal["lecture", "exercise", "mindmap"]


class PublicResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class UserResponse(PublicResponse):
    id: UUID
    username: str
    is_admin: bool


class SessionResponse(PublicResponse):
    user: UserResponse
    csrf_token: str


class CourseResponse(PublicResponse):
    id: str
    name: str
    description: str
    enabled: bool
    knowledge_ready: bool
    version: str


class ChapterResponse(PublicResponse):
    id: str
    title: str
    chapter_number: int
    description: str


class ProfileResponse(PublicResponse):
    version: int = Field(ge=0)
    fields: ProfileFields | None


class DraftMessage(PublicResponse):
    role: Literal["user", "assistant"]
    content: str


class DraftResponse(PublicResponse):
    revision: int = Field(ge=0)
    fields: dict[Literal["knowledge_base", "learning_goal", "preference"], ProfileText]
    messages: list[DraftMessage]


class ConversationResponse(DraftResponse):
    missing: list[str]
    conflicts: list[str]


class MissingModelResponse(PublicResponse):
    version: Literal[0]
    configured: Literal[False]


class SavedModelResponse(PublicResponse):
    version: int = Field(ge=1)
    configured: bool
    protocol: ModelProtocol
    base_url: str
    model_id: str
    has_key: bool
    tested_at: datetime | None


class ModelTestResponse(PublicResponse):
    status: Literal["ok"]
    version: int = Field(ge=1)


class ModelHistoryItem(SavedModelResponse):
    created_at: datetime


class ModelHistoryResponse(PublicResponse):
    items: list[ModelHistoryItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)


class NodeTiming(PublicResponse):
    node: TaskStatus
    elapsed_seconds: float = Field(ge=0)


class TaskTelemetryResponse(PublicResponse):
    task_id: UUID
    protocol: ModelProtocol
    model_id: str
    knowledge_version: str
    prompt_version: str
    nodes: list[NodeTiming]
    model_attempts: int = Field(ge=0)
    transport_retries: int = Field(ge=0)
    usage: list[ModelUsage]


class TaskResponse(PublicResponse):
    id: UUID
    course_id: str
    topic: str
    resource_type: ResourceType
    status: TaskStatus
    profile_version: int = Field(ge=1)
    created_at: datetime
    deadline_at: datetime
    finished_at: datetime | None
    error_code: str | None
    parent_task_id: UUID | None
    resource_id: UUID | None
    content_regenerations: int = Field(ge=0, le=2)
    knowledge_version: str
    prompt_version: str
    telemetry: TaskTelemetryResponse | None


class ResourceMetadata(PublicResponse):
    profile: ProfileSnapshot
    model: ModelSelection
    knowledge_version: str
    prompt_version: str
    ai_notice: str
    automatic_checks: Literal["passed"]
    human_pass: bool


class PlanningSummary(PublicResponse):
    objectives: list[str]
    outline: list[str]


class GenerationProcess(PublicResponse):
    chapter: str | None
    planning: PlanningSummary | None
    regenerations: int = Field(ge=0)
    passed_checks: list[str]
    format_unchanged: bool | None


class ResourceResponse(PublicResponse):
    process: GenerationProcess
    id: UUID
    task_id: UUID
    course_id: str
    topic: str
    content: ResourceDraft
    metadata: ResourceMetadata
    created_at: datetime
    human_pass: bool
    notice: str


class HistoryItem(PublicResponse):
    id: UUID
    title: str
    course_id: str
    topic: str
    resource_type: ResourceType
    created_at: datetime


class HistoryFilters(PublicResponse):
    course_id: str | None
    topic: str
    resource_type: ResourceType | None


class HistoryResponse(PublicResponse):
    items: list[HistoryItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
    filters: HistoryFilters


class SourceResponse(PublicResponse):
    id: UUID
    title: str
    locator: str
    source: str
    license: str
    content: str
    version: str
    index_version: str


class ErrorField(PublicResponse):
    field: str
    message: str


class ErrorDetail(PublicResponse):
    code: str
    message: str
    fields: list[ErrorField] | None = None


class ErrorResponse(PublicResponse):
    error: ErrorDetail
