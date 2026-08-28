"""add pet long-term memory table

Revision ID: 20260829_002
Revises: 20260829_001
Create Date: 2026-08-29
"""

import sqlalchemy as sa
from alembic import op

revision = "20260829_002"
down_revision = "20260829_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pet_memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pet_id",
            sa.Integer(),
            sa.ForeignKey("pets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("end_message_id", sa.Integer(), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("pet_memories")
