"""add course metadata and health columns

Revision ID: 20260906_001
Revises: 20260905_001
Create Date: 2026-09-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260906_001"
down_revision = "20260905_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("courses") as batch:
        batch.add_column(sa.Column("level", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("language", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("health_status", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("http_status", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("health_checked_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("health_error", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "dismiss_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "save_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
    with op.batch_alter_table("course_recommendations") as batch:
        batch.add_column(sa.Column("level", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("language", sa.String(length=8), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("course_recommendations") as batch:
        batch.drop_column("language")
        batch.drop_column("level")
    with op.batch_alter_table("courses") as batch:
        batch.drop_column("save_count")
        batch.drop_column("dismiss_count")
        batch.drop_column("health_error")
        batch.drop_column("health_checked_at")
        batch.drop_column("http_status")
        batch.drop_column("health_status")
        batch.drop_column("language")
        batch.drop_column("level")
