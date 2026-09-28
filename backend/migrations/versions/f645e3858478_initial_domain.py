"""initial_domain

Revision ID: f645e3858478
Revises:
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "f645e3858478"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "courses",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("content_version", sa.String(length=100), nullable=False),
        sa.Column("active_index_version", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
    )
    op.create_table(
        "users",
        sa.Column("username", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("username = lower(username)", name=op.f("ck_users_username_lower")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "knowledge_documents",
        sa.Column("course_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("visibility", sa.String(length=10), nullable=False),
        sa.Column("source_key", sa.String(length=200), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(visibility = 'public' AND owner_id IS NULL) OR "
            "(visibility = 'private' AND owner_id IS NOT NULL)",
            name=op.f("ck_knowledge_documents_visibility_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_knowledge_documents_course_id_courses")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_knowledge_documents_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint(
            "course_id", "source_key", "content_hash", name=op.f("uq_knowledge_documents_course_id")
        ),
    )
    op.create_index(
        op.f("ix_knowledge_documents_course_id"), "knowledge_documents", ["course_id"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_documents_owner_id"), "knowledge_documents", ["owner_id"], unique=False
    )
    op.create_table(
        "login_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_login_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_login_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_login_sessions_expires_at"), "login_sessions", ["expires_at"], unique=False
    )
    op.create_index(op.f("ix_login_sessions_user_id"), "login_sessions", ["user_id"], unique=False)
    op.create_table(
        "model_configurations",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_model_configurations_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_configurations")),
        sa.UniqueConstraint("user_id", "version", name=op.f("uq_model_configurations_user_id")),
    )
    op.create_index(
        op.f("ix_model_configurations_user_id"), "model_configurations", ["user_id"], unique=False
    )
    op.create_table(
        "profile_drafts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_profile_drafts_course_id_courses")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_profile_drafts_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_drafts")),
        sa.UniqueConstraint("user_id", "course_id", name=op.f("uq_profile_drafts_user_id")),
    )
    op.create_table(
        "profile_revisions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name=op.f("ck_profile_revisions_positive_version")),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_profile_revisions_course_id_courses")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_profile_revisions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_revisions")),
        sa.UniqueConstraint(
            "user_id", "course_id", "version", name=op.f("uq_profile_revisions_user_id")
        ),
    )
    op.create_index(
        op.f("ix_profile_revisions_user_id"), "profile_revisions", ["user_id"], unique=False
    )
    op.create_table(
        "generation_tasks",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.String(length=64), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("parent_task_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=20), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("model_configuration_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("content_regenerations", sa.Integer(), nullable=False),
        sa.Column("telemetry", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','planning','generating','validating',"
            "'formatting','completed','failed')",
            name=op.f("ck_generation_tasks_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_generation_tasks_course_id_courses")
        ),
        sa.ForeignKeyConstraint(
            ["model_configuration_id"],
            ["model_configurations.id"],
            name=op.f("fk_generation_tasks_model_configuration_id_model_configurations"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["generation_tasks.id"],
            name=op.f("fk_generation_tasks_parent_task_id_generation_tasks"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_generation_tasks_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_tasks")),
        sa.UniqueConstraint("user_id", "request_key", name=op.f("uq_generation_tasks_user_id")),
    )
    op.create_index(
        op.f("ix_generation_tasks_user_id"), "generation_tasks", ["user_id"], unique=False
    )
    op.create_index(
        "uq_generation_tasks_active_user",
        "generation_tasks",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('completed','failed')"),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("index_version", sa.String(length=100), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name=op.f("fk_knowledge_chunks_document_id_knowledge_documents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
        sa.UniqueConstraint(
            "document_id", "ordinal", "index_version", name=op.f("uq_knowledge_chunks_document_id")
        ),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_document_id"), "knowledge_chunks", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_chunks_index_version"),
        "knowledge_chunks",
        ["index_version"],
        unique=False,
    )
    op.create_table(
        "resources",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.String(length=64), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("human_pass", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_resources_course_id_courses")
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["generation_tasks.id"], name=op.f("fk_resources_task_id_generation_tasks")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_resources_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resources")),
        sa.UniqueConstraint("task_id", name=op.f("uq_resources_task_id")),
    )
    op.create_index(op.f("ix_resources_course_id"), "resources", ["course_id"], unique=False)
    op.create_index(op.f("ix_resources_user_id"), "resources", ["user_id"], unique=False)
    op.create_table(
        "validation_records",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["generation_tasks.id"],
            name=op.f("fk_validation_records_task_id_generation_tasks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_records")),
    )
    op.create_index(
        op.f("ix_validation_records_task_id"), "validation_records", ["task_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_validation_records_task_id"), table_name="validation_records")
    op.drop_table("validation_records")
    op.drop_index(op.f("ix_resources_user_id"), table_name="resources")
    op.drop_index(op.f("ix_resources_course_id"), table_name="resources")
    op.drop_table("resources")
    op.drop_index(op.f("ix_knowledge_chunks_index_version"), table_name="knowledge_chunks")
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(
        "uq_generation_tasks_active_user",
        table_name="generation_tasks",
        postgresql_where=sa.text("status NOT IN ('completed','failed')"),
    )
    op.drop_index(op.f("ix_generation_tasks_user_id"), table_name="generation_tasks")
    op.drop_table("generation_tasks")
    op.drop_index(op.f("ix_profile_revisions_user_id"), table_name="profile_revisions")
    op.drop_table("profile_revisions")
    op.drop_table("profile_drafts")
    op.drop_index(op.f("ix_model_configurations_user_id"), table_name="model_configurations")
    op.drop_table("model_configurations")
    op.drop_index(op.f("ix_login_sessions_user_id"), table_name="login_sessions")
    op.drop_index(op.f("ix_login_sessions_expires_at"), table_name="login_sessions")
    op.drop_table("login_sessions")
    op.drop_index(op.f("ix_knowledge_documents_owner_id"), table_name="knowledge_documents")
    op.drop_index(op.f("ix_knowledge_documents_course_id"), table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_table("users")
    op.drop_table("courses")
    # ### end Alembic commands ###
