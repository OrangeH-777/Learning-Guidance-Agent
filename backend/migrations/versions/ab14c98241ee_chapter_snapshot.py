"""Preserve selected reviewed chapters for generation and citations."""

import sqlalchemy as sa
from alembic import op

revision = "ab14c98241ee"
down_revision = "7c91a04db832"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generation_tasks", sa.Column("chapter_snapshot", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("generation_tasks", "chapter_snapshot")
