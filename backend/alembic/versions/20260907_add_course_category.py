"""add course category

Revision ID: 20260907_001
Revises: 20260906_001
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op

revision = "20260907_001"
down_revision = "20260906_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("category", sa.String(length=32), nullable=True))
    with op.batch_alter_table("course_recommendations") as batch:
        batch.add_column(sa.Column("category", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("course_recommendations") as batch:
        batch.drop_column("category")
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("category")
