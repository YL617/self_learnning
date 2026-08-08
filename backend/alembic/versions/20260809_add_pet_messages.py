"""add pet messages

Revision ID: 20260809_001
Revises: 20260806_003
Create Date: 2026-08-09
"""

import sqlalchemy as sa
from alembic import op

revision = "20260809_001"
down_revision = "20260806_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pet_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pet_id",
            sa.Integer(),
            sa.ForeignKey("pets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="assistant"),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="chat"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("pet_messages")
