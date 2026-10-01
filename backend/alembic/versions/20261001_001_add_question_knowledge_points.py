"""add question knowledge points

Revision ID: 20261001_001
Revises: 20260909_001
Create Date: 2026-10-01

仅创建 Phase 2 结构化关联表（Schema only）。
Legacy 自由文本回填由独立脚本 scripts/backfill_question_knowledge_points.py 负责，
migration 不携带任何业务数据迁移。
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_001"
down_revision = "20260909_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_knowledge_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="primary"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="CASCADE",
            name="fk_question_knowledge_points_question_id",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="RESTRICT",
            name="fk_question_knowledge_points_knowledge_point_id",
        ),
        sa.UniqueConstraint(
            "question_id",
            "knowledge_point_id",
            name="uq_question_knowledge_points_pair",
        ),
    )
    op.create_index(
        "ix_question_knowledge_points_knowledge_point_id",
        "question_knowledge_points",
        ["knowledge_point_id"],
    )


def downgrade() -> None:
    # MySQL 要求先解除 FK 依赖，才能删除其使用的索引；batch 模式兼容 SQLite。
    with op.batch_alter_table("question_knowledge_points") as batch:
        batch.drop_constraint(
            "fk_question_knowledge_points_question_id", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_question_knowledge_points_knowledge_point_id", type_="foreignkey"
        )
    op.drop_index(
        "ix_question_knowledge_points_knowledge_point_id",
        table_name="question_knowledge_points",
    )
    op.drop_table("question_knowledge_points")
