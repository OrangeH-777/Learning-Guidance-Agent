"""Add an explicit administrator role; existing users remain ordinary users."""

import sqlalchemy as sa
from alembic import op

revision = "7c91a04db832"
down_revision = "308aa7fa06a9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade():
    op.drop_column("users", "is_admin")
