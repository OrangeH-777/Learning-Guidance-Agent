from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from agents.retrieval.catalog import Identifier, SourceEntry
from backend.app.schemas.inputs import InputModel
from backend.app.schemas.responses import PublicResponse
from backend.app.services.material_text import MAX_TEXT_CHARACTERS

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class CourseCreate(InputModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""


class MaterialSave(InputModel):
    expected_version: Label
    source_id: Identifier | None = None
    title: Label
    source_url: Annotated[str, StringConstraints(max_length=2000)]
    section: Label
    license: Label
    content: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_CHARACTERS)]
    confirmed: Literal[True]

    @field_validator("source_url")
    @classmethod
    def source_link(cls, value):
        return SourceEntry.http_source(value)

    @field_validator("content")
    @classmethod
    def text_content(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Empty or invalid text")
        return value


class MaterialPreview(PublicResponse):
    content: str
    warnings: list[str]
    characters: int


class MaterialEntry(PublicResponse):
    id: str
    title: str
    source_url: str
    section: str
    license: str
    review_status: str


class MaterialDetail(MaterialEntry):
    content: str
    version: str


class AdminCourse(PublicResponse):
    id: str
    name: str
    version: str
    active_index_version: str | None
    sources: list[MaterialEntry]


class MaterialSaved(PublicResponse):
    source_id: str
    version: str


class IndexRequest(InputModel):
    expected_version: Label
    acknowledge_costs: Literal[True]
    allow_unreviewed: bool = False


class IndexJob(PublicResponse):
    id: str
    course_id: str
    index_version: str
    status: Literal["running", "indexed", "unchanged", "failed", "interrupted"]
    chunks: int = Field(default=0, ge=0)
    error: str | None = None
