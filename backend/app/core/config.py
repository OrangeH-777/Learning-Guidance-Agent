"""Infrastructure configuration only; business settings are reserved in .env.example."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr = SecretStr("")
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    model_credential_encryption_key: SecretStr = SecretStr("")
    model_credential_previous_keys: list[str] = Field(default_factory=list, repr=False)
    session_ttl_seconds: int = Field(default=7200, ge=60, le=86400)
    cookie_secure: bool = False
    admin_username: str = ""
    admin_password: SecretStr = SecretStr("")
    allowed_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:8000",
    ]
    model_endpoint_allowlist: list[str] = []
    embedding_protocol: str = ""
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = ""
    embedding_dimensions: int | None = None
    embedding_index_version: str = ""
    retrieval_top_k: int = Field(default=6, ge=1, le=50)
    retrieval_max_cosine_distance: float = Field(default=0.8, ge=0, le=2)
    knowledge_chunk_characters: int = Field(default=1200, ge=200, le=5000)
    public_knowledge_dir: str = "knowledge"
    model_call_timeout_seconds: float = Field(default=60, gt=0, le=60)
    task_timeout_seconds: float = Field(default=180, gt=0, le=180)
    content_regeneration_limit: int = Field(default=2, ge=0, le=2)
    model_transport_retry_limit: int = Field(default=1, ge=0, le=1)
    global_generation_limit: int = Field(default=2, ge=1, le=2)
    user_active_task_limit: int = Field(default=1, ge=1, le=1)
    task_queue_capacity: int | None = Field(default=None, ge=0)

    @field_validator("embedding_dimensions", "task_queue_capacity", mode="before")
    @classmethod
    def empty_optional_number(cls, value):
        return None if value == "" else value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw and not raw.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg://")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
