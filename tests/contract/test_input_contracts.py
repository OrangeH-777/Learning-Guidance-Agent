"""Known source boundary cases TC002/003/005/010, without database or authentication."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.schemas.inputs import ConversationInput, ProfileFields, RegistrationInput


def registration(**overrides):
    values = {
        "username": "student_a",
        "password": "Test1234!",
        "password_confirmation": "Test1234!",
    }
    values.update(overrides)
    return RegistrationInput.model_validate(values)


@pytest.mark.parametrize("size,valid", [(3, False), (4, True), (20, True), (21, False)])
def test_username_boundaries(size, valid):
    if valid:
        assert registration(username="A" * size).username == "a" * size
    else:
        with pytest.raises(ValidationError):
            registration(username="A" * size)


@pytest.mark.parametrize("username", ["user name", "user\n", "学号1234", "user-name", 12345])
def test_invalid_usernames_are_not_normalized_into_valid_accounts(username):
    with pytest.raises(ValidationError):
        registration(username=username)


@pytest.mark.parametrize("size,valid", [(7, False), (8, True), (64, True), (65, False)])
def test_password_length_and_no_silent_truncation(size, valid):
    password = "A1" + "🌳" * (size - 2)
    if valid:
        parsed = registration(password=password, password_confirmation=password)
        assert parsed.password.get_secret_value() == password
        assert "password_confirmation" not in parsed.model_dump()
        assert password not in repr(parsed)
    else:
        with pytest.raises(ValidationError):
            registration(password=password, password_confirmation=password)


@pytest.mark.parametrize("password", ["abcdefgh", "12345678"])
def test_password_requires_letters_and_digits(password):
    with pytest.raises(ValidationError):
        registration(password=password, password_confirmation=password)


def test_password_confirmation_must_match():
    with pytest.raises(ValidationError):
        registration(password_confirmation="Mismatch123")


@pytest.mark.parametrize("field", ["knowledge_base", "learning_goal", "preference"])
@pytest.mark.parametrize("size,valid", [(0, False), (1, True), (500, True), (501, False)])
def test_profile_boundaries_use_unicode_codepoints(field, size, valid):
    values = {"knowledge_base": "初学", "learning_goal": "掌握栈", "preference": "无偏好"}
    values[field] = "🌳" * size
    if valid:
        assert len(getattr(ProfileFields(**values), field)) == size
    else:
        with pytest.raises(ValidationError):
            ProfileFields(**values)


@pytest.mark.parametrize("size,valid", [(0, False), (1, True), (1000, True), (1001, False)])
def test_conversation_boundaries(size, valid):
    if valid:
        assert len(ConversationInput(content="字" * size).content) == size
    else:
        with pytest.raises(ValidationError):
            ConversationInput(content="字" * size)


def test_request_errors_do_not_echo_password_or_unknown_secret_keys():
    app = create_app(Settings(database_url="", _env_file=None))

    @app.post("/test-only-registration")
    def validate_registration(body: RegistrationInput):
        return {"username": body.username}

    with TestClient(app) as client:
        response = client.post(
            "/test-only-registration",
            json={
                "username": "bad",
                "password": "SECRET_MARKER",
                "password_confirmation": "SECRET_MARKER",
                "SECRET_KEY_MARKER": "sensitive-value",
            },
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert "body.username" in response.text
    assert "SECRET_MARKER" not in response.text
    assert "SECRET_KEY_MARKER" not in response.text
    assert "sensitive-value" not in response.text
