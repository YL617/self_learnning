"""add membership_level to users

Revision ID: 20260806_002
Revises: 20260806_001
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_002"
down_revision = "20260806_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("membership_level", sa.String(length=32), nullable=False, server_default="free"),
    )


def downgrade() -> None:
    op.drop_column("users", "membership_level")
