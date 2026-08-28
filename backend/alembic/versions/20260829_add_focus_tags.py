"""add focus tags and session tag color

Revision ID: 20260829_001
Revises: 20260810_002
Create Date: 2026-08-29
"""

import sqlalchemy as sa
from alembic import op

revision = "20260829_001"
down_revision = "20260810_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "focus_sessions",
        sa.Column("tag_color", sa.String(length=16), nullable=True),
    )
    op.create_table(
        "focus_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column(
            "color",
            sa.String(length=16),
            nullable=False,
            server_default="#0f766e",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_focus_tags_user_name"),
    )


def downgrade() -> None:
    op.drop_table("focus_tags")
    op.drop_column("focus_sessions", "tag_color")
