"""Confirmed input boundaries from the second-cycle specification.

Course ownership, profile versions and model selection remain service responsibilities.
"""

import re
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

Username = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_]{4,20}$")]
ProfileText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)]
TopicText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100)]
ConversationText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
RequestKey = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class RegistrationInput(InputModel):
    username: Username
    password: SecretStr = Field(repr=False)
    password_confirmation: SecretStr = Field(repr=False, exclude=True)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()

    @field_validator("password", "password_confirmation")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 8 <= len(password) <= 64:
            raise ValueError("Password must contain 8 to 64 characters")
        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            raise ValueError("Password must include a letter and a digit")
        return value

    @model_validator(mode="after")
    def passwords_match(self) -> Self:
        if self.password.get_secret_value() != self.password_confirmation.get_secret_value():
            raise ValueError("Password confirmation does not match")
        return self


class ProfileFields(InputModel):
    knowledge_base: ProfileText
    learning_goal: ProfileText
    preference: ProfileText

    @field_validator("knowledge_base", "learning_goal", "preference")
    @classmethod
    def reject_blank_fields(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Profile fields must not be blank")
        return value


class ConversationInput(InputModel):
    content: ConversationText

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Conversation content must not be blank")
        return value


def normalize_username_for_lookup(username: str) -> str:
    """Share the exact registration identity rule with later authentication lookups."""
    if re.fullmatch(r"[A-Za-z0-9_]{4,20}", username) is None:
        raise ValueError("Invalid username format")
    return username.lower()
