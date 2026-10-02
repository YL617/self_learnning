"""add knowledge_points.node_type

Revision ID: 20261002_005
Revises: 20261001_004
Create Date: 2026-10-02

大阶段 4 P0 修复：知识节点类型（container | concept）。

  - `knowledge_points.node_type`：`VARCHAR(16) NOT NULL server_default 'concept'`。
    NOT NULL + server_default 让加列对存量行免回填；生产实测 0 行，线上为纯空操作。
    default 取 `concept` 是 **fail-loud** 原则：漏写类型时宁可让目录被当成知识点
    （可见错误），也不让真知识点被静默降级（静默丢功能）。
  - `ix_knowledge_points_node_type`：所有热点查询都会 `WHERE node_type='concept'`
    （推荐 / AI 标注词表 / 规模统计），需要独立索引。
  - `ck_knowledge_points_node_type`：把词表钉死在 DB 层，照抄既有
    `ck_knowledge_points_difficulty` 的范式。

SQLite 不支持 `ALTER TABLE ADD CONSTRAINT`，故 CHECK 走 `batch_alter_table` 重建；
MySQL 下 batch 是直通，落地为普通 ALTER。顺序沿用 `20261001_004` 的
「先加列 → 再建索引 → 再批量建约束」，保证 upgrade/downgrade/upgrade 三连幂等。

schema-only：不含任何业务数据迁移；本 revision 不修改任何历史对象。
无需数据回填：历史行一律由 server_default 落为 `concept`，与现状语义一致
（现状就是全部都当可学习知识点）。
"""

import sqlalchemy as sa

from alembic import op

revision = "20261002_005"
down_revision = "20261001_004"
branch_labels = None
depends_on = None

KP_TABLE = "knowledge_points"


def upgrade() -> None:
    op.add_column(
        KP_TABLE,
        sa.Column(
            "node_type",
            sa.String(length=16),
            nullable=False,
            server_default="concept",
        ),
    )
    op.create_index("ix_knowledge_points_node_type", KP_TABLE, ["node_type"])
    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT → 必须走 batch 重建（与 004 同范式）。
    with op.batch_alter_table(KP_TABLE) as batch:
        batch.create_check_constraint(
            "ck_knowledge_points_node_type",
            "node_type IN ('container', 'concept')",
        )


def downgrade() -> None:
    with op.batch_alter_table(KP_TABLE) as batch:
        batch.drop_constraint("ck_knowledge_points_node_type", type_="check")
    op.drop_index("ix_knowledge_points_node_type", table_name=KP_TABLE)
    op.drop_column(KP_TABLE, "node_type")
