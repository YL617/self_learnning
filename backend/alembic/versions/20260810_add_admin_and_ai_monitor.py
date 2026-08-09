"""add admin role and ai monitor tables

Revision ID: 20260810_001
Revises: 20260809_002
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op

revision = "20260810_001"
down_revision = "20260809_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("nickname", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("avatar_path", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
    )
    op.create_table(
        "ai_provider_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False, index=True),
        sa.Column("total_balance", sa.String(length=64), nullable=False, server_default="0"),
        sa.Column("granted_balance", sa.String(length=64), nullable=False, server_default="0"),
        sa.Column("topped_up_balance", sa.String(length=64), nullable=False, server_default="0"),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ai_usage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False, index=True),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "usage_date", name="uq_ai_usage_provider_date"),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_records")
    op.drop_table("ai_provider_snapshots")
    op.drop_column("users", "role")
    op.drop_column("users", "avatar_path")
    op.drop_column("users", "nickname")
