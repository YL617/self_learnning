"""add onboarding fields to user_profiles

Revision ID: 20260806_001
Revises:
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_001"
down_revision = None
branch_labels = None
depends_on = None

COLUMNS = [
    "school_level",
    "pain_point",
    "learning_style",
    "weekly_study_minutes",
    "available_time_slots",
    "onboarding_completed",
    "onboarding_completed_at",
]


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("school_level", sa.String(length=64), nullable=True))
    op.add_column("user_profiles", sa.Column("pain_point", sa.Text(), nullable=True))
    op.add_column("user_profiles", sa.Column("learning_style", sa.Text(), nullable=True))
    op.add_column(
        "user_profiles",
        sa.Column("weekly_study_minutes", sa.Integer(), nullable=False, server_default="420"),
    )
    op.add_column("user_profiles", sa.Column("available_time_slots", sa.Text(), nullable=True))
    op.add_column(
        "user_profiles",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("user_profiles", sa.Column("onboarding_completed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("user_profiles", column)
