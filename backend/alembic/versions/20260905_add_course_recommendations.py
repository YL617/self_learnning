"""add course recommendations table

Revision ID: 20260905_001
Revises: 20260829_002
Create Date: 2026-09-05
"""

import sqlalchemy as sa
from alembic import op

revision = "20260905_001"
down_revision = "20260829_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("study_plans.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "platform", sa.String(length=64), nullable=False, server_default="在线课程"
        ),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=64), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("course_recommendations")
