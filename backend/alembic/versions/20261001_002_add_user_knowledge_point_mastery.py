"""add user knowledge point mastery

Revision ID: 20261001_002
Revises: 20261001_001
Create Date: 2026-10-01

大阶段 2（学习状态闭环）：
  1. 新建 user_knowledge_point_mastery（用户维度知识点掌握度）。
     UNIQUE(user_id, knowledge_point_id) 已提供 user_id 前缀索引，
     因此只需为反向查询（按知识点统计）保留 knowledge_point_id 索引。
  2. 为 wrong_book_items 补 UNIQUE(user_id, question_id)：
     "一个用户 + 一道题只保留一条错题记录" 由 DB 兜底，而非只靠应用层查重。

schema-only：不含任何业务数据迁移。
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_002"
down_revision = "20261001_001"
branch_labels = None
depends_on = None

MASTERY_TABLE = "user_knowledge_point_mastery"


def upgrade() -> None:
    op.create_table(
        MASTERY_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("mastery_score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_answered_at", sa.DateTime(), nullable=True),
        sa.Column("last_correct_at", sa.DateTime(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_user_knowledge_point_mastery_user_id",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="RESTRICT",
            name="fk_user_knowledge_point_mastery_knowledge_point_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "knowledge_point_id",
            name="uq_user_knowledge_point_mastery_pair",
        ),
    )
    op.create_index(
        "ix_user_knowledge_point_mastery_knowledge_point_id",
        MASTERY_TABLE,
        ["knowledge_point_id"],
    )

    with op.batch_alter_table("wrong_book_items") as batch:
        batch.create_unique_constraint(
            "uq_wrong_book_items_user_question", ["user_id", "question_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("wrong_book_items") as batch:
        batch.drop_constraint("uq_wrong_book_items_user_question", type_="unique")

    op.drop_index(
        "ix_user_knowledge_point_mastery_knowledge_point_id", table_name=MASTERY_TABLE
    )
    # MySQL 要求先解除 FK 依赖，才能删除其使用的索引；batch 模式兼容 SQLite。
    with op.batch_alter_table(MASTERY_TABLE) as batch:
        batch.drop_constraint(
            "fk_user_knowledge_point_mastery_user_id", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_user_knowledge_point_mastery_knowledge_point_id", type_="foreignkey"
        )
    op.drop_table(MASTERY_TABLE)
