"""add knowledge point prerequisites

Revision ID: 20261001_003
Revises: 20261001_002
Create Date: 2026-10-01

大阶段 3（推荐系统 V1）：新增知识点前置依赖边表。

  - `knowledge_point_prerequisites` 表达「必须先学前置，才能学后置」的多对多 DAG，
    与 `knowledge_points.parent_id`（归属层级树）语义不同，故单独建表。
  - UNIQUE(knowledge_point_id, prerequisite_id) 覆盖 knowledge_point_id 前缀索引，
    因此只需为反向查询（按前置找后置 / 解锁统计）保留 prerequisite_id 索引。
  - CHECK 约束从 DB 层拦截自环（成环由 PrerequisiteService 写入前做可达性检查）。
  - `strength` 0~100：>= 阻塞阈值算硬前置，低于阈值仅作学习顺序建议。

schema-only：不含任何业务数据迁移；本 revision 不修改任何历史表。
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_003"
down_revision = "20261001_002"
branch_labels = None
depends_on = None

PREREQ_TABLE = "knowledge_point_prerequisites"


def upgrade() -> None:
    op.create_table(
        PREREQ_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("prerequisite_id", sa.Integer(), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"],
            ["knowledge_points.id"],
            ondelete="RESTRICT",
            name="fk_knowledge_point_prerequisites_knowledge_point_id",
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_id"],
            ["knowledge_points.id"],
            ondelete="RESTRICT",
            name="fk_knowledge_point_prerequisites_prerequisite_id",
        ),
        sa.UniqueConstraint(
            "knowledge_point_id",
            "prerequisite_id",
            name="uq_knowledge_point_prerequisites_pair",
        ),
        sa.CheckConstraint(
            "knowledge_point_id <> prerequisite_id",
            name="ck_knowledge_point_prerequisites_no_self_loop",
        ),
    )
    op.create_index(
        "ix_knowledge_point_prerequisites_prerequisite_id",
        PREREQ_TABLE,
        ["prerequisite_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_point_prerequisites_prerequisite_id", table_name=PREREQ_TABLE
    )
    # MySQL 要求先解除 FK 依赖，才能删除其使用的索引；batch 模式兼容 SQLite。
    with op.batch_alter_table(PREREQ_TABLE) as batch:
        batch.drop_constraint(
            "fk_knowledge_point_prerequisites_knowledge_point_id", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_knowledge_point_prerequisites_prerequisite_id", type_="foreignkey"
        )
    op.drop_table(PREREQ_TABLE)
