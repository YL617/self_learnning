"""add knowledge points

Revision ID: 20260908_001
Revises: 20260907_001
Create Date: 2026-09-08
"""

import sqlalchemy as sa

from alembic import op

revision = "20260908_001"
down_revision = "20260907_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=100), nullable=False),
        sa.Column("normalized_subject", sa.String(length=100), nullable=False),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_points.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_subject",
            "normalized_name",
            name="uq_knowledge_points_normalized_subject_name",
        ),
    )
    op.create_index("ix_knowledge_points_id", "knowledge_points", ["id"])
    op.create_index("ix_knowledge_points_parent_id", "knowledge_points", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_points_parent_id", table_name="knowledge_points")
    op.drop_index("ix_knowledge_points_id", table_name="knowledge_points")
    op.drop_table("knowledge_points")
