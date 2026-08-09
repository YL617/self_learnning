"""add membership expiry, activation codes and ai daily usage

Revision ID: 20260810_002
Revises: 20260810_001
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op

revision = "20260810_002"
down_revision = "20260810_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("membership_expires_at", sa.DateTime(), nullable=True))
    op.create_table(
        "activation_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True, index=True),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unused"),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "used_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ai_daily_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "usage_date", name="uq_ai_daily_usage_user_date"),
    )


def downgrade() -> None:
    op.drop_table("ai_daily_usage")
    op.drop_table("activation_codes")
    op.drop_column("users", "membership_expires_at")
