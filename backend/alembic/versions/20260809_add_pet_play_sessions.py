"""add pet play sessions

Revision ID: 20260809_002
Revises: 20260809_001
Create Date: 2026-08-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260809_002"
down_revision = "20260809_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pets", sa.Column("play_date", sa.Date(), nullable=True))
    op.add_column(
        "pets",
        sa.Column("play_count_today", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("pets", sa.Column("playing_until", sa.DateTime(), nullable=True))
    op.create_table(
        "pet_play_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pet_id",
            sa.Integer(),
            sa.ForeignKey("pets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("coin_cost", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("mood_gain", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("exp_gain", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("hunger_loss", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pet_play_sessions")
    op.drop_column("pets", "playing_until")
    op.drop_column("pets", "play_count_today")
    op.drop_column("pets", "play_date")
