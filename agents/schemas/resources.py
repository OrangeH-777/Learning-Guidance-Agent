"""Resource draft contracts shared by workflow validation and API integration.

A valid shape does not imply factual correctness, authorized sources or publication.
Those are separate workflow and persistence checks.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
Title = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ResourceBase(ContractModel):
    title: Title
    source_ids: list[Text] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Source identifiers must be unique")
        return self


class LectureSection(ContractModel):
    heading: Text
    explanation: Text


class LectureExample(ContractModel):
    title: Text
    content: Text


class LectureResource(ResourceBase):
    resource_type: Literal["lecture"]
    learning_objectives: list[Text] = Field(min_length=1)
    prerequisites: list[Text] = Field(min_length=1)
    sections: list[LectureSection] = Field(min_length=1)
    examples: list[LectureExample] = Field(min_length=1)
    summary: Text


class ChoiceOption(ContractModel):
    label: Text
    content: Text


class SingleChoiceQuestion(ContractModel):
    question_type: Literal["single_choice"]
    question_id: Text
    prompt: Text
    options: list[ChoiceOption] = Field(min_length=2)
    answer: Text
    analysis: Text

    @model_validator(mode="after")
    def validate_options_and_answer(self) -> Self:
        labels = [option.label for option in self.options]
        if len(set(labels)) != len(labels):
            raise ValueError("Choice labels must be unique")
        if self.answer not in labels:
            raise ValueError("The answer must identify one of the choices")
        return self


class ShortAnswerQuestion(ContractModel):
    question_type: Literal["short_answer"]
    question_id: Text
    prompt: Text
    answer: Text
    analysis: Text


Question = Annotated[
    SingleChoiceQuestion | ShortAnswerQuestion, Field(discriminator="question_type")
]


class ExerciseResource(ResourceBase):
    resource_type: Literal["exercise"]
    questions: list[Question] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_question_ids(self) -> Self:
        ids = [question.question_id for question in self.questions]
        if len(set(ids)) != len(ids):
            raise ValueError("Question identifiers must be unique")
        return self


class MindmapNode(ContractModel):
    label: Text
    children: list["MindmapNode"] = Field(default_factory=list)


class MindmapResource(ResourceBase):
    resource_type: Literal["mindmap"]
    root: MindmapNode

    @model_validator(mode="after")
    def root_has_branches(self) -> Self:
        if not self.root.children:
            raise ValueError("A mindmap must have a root and at least one branch")
        return self


ResourceDraft = Annotated[
    LectureResource | ExerciseResource | MindmapResource,
    Field(discriminator="resource_type"),
]
resource_draft_adapter = TypeAdapter(ResourceDraft)
