"""add plan chat tables

Revision ID: 20260806_003
Revises: 20260806_002
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_003"
down_revision = "20260806_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="collecting"),
        sa.Column("collected_context", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("draft_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "plan_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("plan_chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("plan_chat_messages")
    op.drop_table("plan_chat_sessions")
