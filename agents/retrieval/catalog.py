"""Validated YAML catalog; content must resolve inside the selected course directory."""

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, StringConstraints, field_validator

from agents.schemas.resources import ContractModel, Text

Identifier = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]{0,63}$")]
ChapterNumber = Annotated[int, Field(strict=True, ge=1, le=999999)]
ChapterDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class SourceEntry(ContractModel):
    id: Identifier
    title: Text
    file: Text
    source_url: Text
    section: Text
    license: Text
    version: Text
    review_status: str
    chapter_number: ChapterNumber | None = None
    description: ChapterDescription = ""

    @field_validator("source_url")
    @classmethod
    def http_source(cls, value):
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Source URL must be an HTTP(S) reference without credentials")
        return value


class CourseManifest(ContractModel):
    id: Identifier
    name: Text
    description: Text
    version: Text
    enabled: bool = Field(strict=True)
    maintainer: Text
    topics: list[Text] = Field(min_length=1)
    prerequisites: list[Text]
    sources: list[SourceEntry]


def read_course(directory: Path) -> CourseManifest:
    path = directory / "course.yaml"
    raw = path.read_text(encoding="utf-8")
    if len(raw) > 1024 * 1024:
        raise ValueError("Course manifest is too large")
    course = CourseManifest.model_validate(yaml.safe_load(raw))
    if course.id != directory.name:
        raise ValueError("Course ID must match its directory")
    if len({source.id for source in course.sources}) != len(course.sources):
        raise ValueError("Source IDs must be unique within a course")
    for source in course.sources:
        read_source(directory, source)
    return course


def read_source(directory: Path, source: SourceEntry) -> str:
    root = directory.resolve()
    path = (root / source.file).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() != ".md":
        raise ValueError("Knowledge source must be a Markdown file inside the course directory")
    value = path.read_text(encoding="utf-8")
    if not value.strip() or len(value) > 5_000_000:
        raise ValueError("Knowledge content is empty or too large")
    return value
