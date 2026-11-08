"""PostgreSQL entities; revisions and source chunks are immutable after publication."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Identity, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("username = lower(username)", name="username_lower"),)
    username: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class LoginSession(Identity, Base):
    __tablename__ = "login_sessions"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    content_version: Mapped[str] = mapped_column(String(100))
    active_index_version: Mapped[str | None] = mapped_column(String(100))


class ProfileRevision(Identity, Base):
    __tablename__ = "profile_revisions"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", "version"),
        CheckConstraint("version > 0", name="positive_version"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    version: Mapped[int] = mapped_column(Integer)
    fields: Mapped[dict] = mapped_column(JSON)


class ProfileDraft(Identity, Base):
    __tablename__ = "profile_drafts"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    messages: Mapped[list] = mapped_column(JSON, default=list)


class ModelConfiguration(Identity, Base):
    __tablename__ = "model_configurations"
    __table_args__ = (UniqueConstraint("user_id", "version"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(String(200))
    encrypted_key: Mapped[str] = mapped_column(Text)
    tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired: Mapped[bool] = mapped_column(Boolean, default=False)


class GenerationTask(Identity, Base):
    __tablename__ = "generation_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key"),
        CheckConstraint(
            "status IN ('queued','planning','generating','validating','formatting',"
            "'completed','failed')",
            name="valid_status",
        ),
        Index(
            "uq_generation_tasks_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("status NOT IN ('completed','failed')"),
        ),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    request_key: Mapped[str] = mapped_column(String(64))
    request_digest: Mapped[str] = mapped_column(String(64))
    parent_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("generation_tasks.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    topic: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(20))
    profile_version: Mapped[int] = mapped_column(Integer)
    profile_snapshot: Mapped[dict] = mapped_column(JSON)
    model_configuration_id: Mapped[UUID] = mapped_column(ForeignKey("model_configurations.id"))
    chapter_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    knowledge_version: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(100))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(40))
    content_regenerations: Mapped[int] = mapped_column(Integer, default=0)
    telemetry: Mapped[dict] = mapped_column(JSON, default=dict)


class Resource(Identity, Base):
    __tablename__ = "resources"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("generation_tasks.id"), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    topic: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(20))
    content: Mapped[dict] = mapped_column(JSON)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON)
    source_ids: Mapped[list] = mapped_column(JSON)
    human_pass: Mapped[bool] = mapped_column(Boolean, default=False)


class ValidationRecord(Identity, Base):
    __tablename__ = "validation_records"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("generation_tasks.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean)
    checks: Mapped[dict] = mapped_column(JSON)


class KnowledgeDocument(Identity, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "(visibility = 'public' AND owner_id IS NULL) OR "
            "(visibility = 'private' AND owner_id IS NOT NULL)",
            name="visibility_owner",
        ),
        Index(
            "uq_public_document_revision",
            "course_id",
            "source_key",
            "version",
            unique=True,
            postgresql_where=text("visibility = 'public'"),
        ),
        Index(
            "uq_private_document_revision",
            "course_id",
            "owner_id",
            "source_key",
            "version",
            unique=True,
            postgresql_where=text("visibility = 'private'"),
        ),
    )
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(10), default="public")
    source_key: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(Text)
    license: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(100))


class KnowledgeChunk(Identity, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "ordinal", "index_version"),)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    locator: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    index_version: Mapped[str] = mapped_column(String(100), index=True)
    embedding_model: Mapped[str] = mapped_column(String(200))
    dimensions: Mapped[int] = mapped_column(Integer)
    # Dimensions are validated against deployment config. Separate version filters prevent mixing.
    embedding: Mapped[list[float]] = mapped_column(Vector())
