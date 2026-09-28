"""Immutable, credential-free node inputs shared by retrieval and workflow execution."""

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from agents.schemas.models import FrozenContract, ModelSelection, NonBlank


class ProfileSnapshot(FrozenContract):
    version: int = Field(strict=True, ge=1)
    knowledge_base: NonBlank = Field(repr=False)
    learning_goal: NonBlank = Field(repr=False)
    preference: NonBlank = Field(repr=False)


class WorkflowInput(FrozenContract):
    task_id: UUID
    user_id: UUID
    course_id: NonBlank
    topic: NonBlank
    resource_type: Literal["lecture", "exercise", "mindmap"]
    profile: ProfileSnapshot
    model: ModelSelection
    knowledge_version: NonBlank
    prompt_version: NonBlank


class SourceFragment(FrozenContract):
    id: UUID
    course_id: NonBlank
    visibility: Literal["public", "private"]
    owner_id: UUID | None
    content: NonBlank = Field(repr=False)
    locator: NonBlank
    index_version: NonBlank

    @model_validator(mode="after")
    def visibility_owner(self):
        if (self.visibility == "public") != (self.owner_id is None):
            raise ValueError("Source visibility and ownership disagree")
        return self


class ResourcePlan(FrozenContract):
    objectives: tuple[NonBlank, ...] = Field(min_length=1)
    difficulty: NonBlank
    prerequisites: tuple[NonBlank, ...] = Field(min_length=1)
    outline: tuple[NonBlank, ...] = Field(min_length=1)
    personalization: NonBlank


class ContentVerdict(FrozenContract):
    relevant: bool = Field(strict=True)
    supported: bool = Field(strict=True)
    facts_correct: bool = Field(strict=True)
    answers_consistent: bool = Field(strict=True)
    safe: bool = Field(strict=True)
    issues: tuple[NonBlank, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.relevant
            and self.supported
            and self.facts_correct
            and self.answers_consistent
            and self.safe
            and not self.issues
        )
