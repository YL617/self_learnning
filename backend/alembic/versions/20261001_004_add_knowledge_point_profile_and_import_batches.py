"""add knowledge point profile columns and import batches

Revision ID: 20261001_004
Revises: 20261001_003
Create Date: 2026-10-01

大阶段 4 M1：知识点内容元数据 + 批量导入批次。

  - 新建 `knowledge_point_import_batches`（批次追溯与回滚），必须先于加列执行：
    `knowledge_points.import_batch_id` 的外键指向它。
  - `knowledge_points` 追加 5 列，全部 **nullable、无 server_default**，因此对
    存量的 0 行（生产实测）与未来任意数据量都不需要回填。
  - `uq_knowledge_points_code`：稳定编码唯一。两库的唯一索引都允许多个 NULL，
    所以历史行不填 code 也不会互相冲突。
  - `ck_knowledge_points_difficulty`：把难度词表钉死在 DB 层。全项目只允许
    easy/medium/hard 一套（与 plan_items.difficulty、MasteryService 同源）。
    `difficulty` 仅用于展示与推荐，**不参与掌握度计算**。
  - `ix_knowledge_points_import_batch_id`：按批次反查导入产物的唯一查询路径；
    同时被 MySQL 用作 `fk_knowledge_points_import_batch_id` 的支撑索引，
    避免 InnoDB 再自动补一个同名索引导致 drift。

SQLite 不支持 `ALTER TABLE ADD CONSTRAINT`，因此唯一约束 / 外键 / CHECK 统一走
`batch_alter_table` 重建；MySQL 下 batch 是直通，落地为普通 ALTER。
不可逆信息为零：downgrade 只删除本 revision 新建的对象。

schema-only：不含任何业务数据迁移；本 revision 不修改任何历史对象。
"""

import sqlalchemy as sa

from alembic import op

revision = "20261001_004"
down_revision = "20261001_003"
branch_labels = None
depends_on = None

BATCH_TABLE = "knowledge_point_import_batches"
KP_TABLE = "knowledge_points"

KP_NEW_COLUMNS = ("code", "aliases", "difficulty", "estimated_minutes", "import_batch_id")


def upgrade() -> None:
    # ---- 1) 先建被引用表 ----
    op.create_table(
        BATCH_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_format", sa.String(length=16), nullable=False, server_default="tsv"),
        sa.Column("conflict_strategy", sa.String(length=16), nullable=False, server_default="skip"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="applied"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_parent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_knowledge_point_import_batches_user_id",
        ),
        sa.CheckConstraint(
            "status IN ('applied', 'failed', 'rolled_back')",
            name="ck_knowledge_point_import_batches_status",
        ),
        sa.CheckConstraint(
            "conflict_strategy IN ('skip', 'update_empty')",
            name="ck_knowledge_point_import_batches_conflict_strategy",
        ),
        sa.CheckConstraint(
            "total_rows >= 0 AND created_count >= 0 AND updated_count >= 0 "
            "AND skipped_count >= 0 AND failed_count >= 0 AND auto_parent_count >= 0",
            name="ck_knowledge_point_import_batches_counts",
        ),
    )
    op.create_index(
        "ix_knowledge_point_import_batches_user_id", BATCH_TABLE, ["user_id"]
    )

    # ---- 2) knowledge_points 追加列（nullable，无需回填）----
    op.add_column(KP_TABLE, sa.Column("code", sa.String(length=64), nullable=True))
    op.add_column(KP_TABLE, sa.Column("aliases", sa.JSON(), nullable=True))
    op.add_column(KP_TABLE, sa.Column("difficulty", sa.String(length=16), nullable=True))
    op.add_column(KP_TABLE, sa.Column("estimated_minutes", sa.Integer(), nullable=True))
    op.add_column(KP_TABLE, sa.Column("import_batch_id", sa.Integer(), nullable=True))
    # 索引先建：MySQL 会直接复用它作为 FK 支撑索引，不再自动补索引。
    op.create_index(
        "ix_knowledge_points_import_batch_id", KP_TABLE, ["import_batch_id"]
    )

    # ---- 3) 约束：SQLite 必须走 batch 重建，MySQL 为直通 ALTER ----
    with op.batch_alter_table(KP_TABLE) as batch:
        batch.create_unique_constraint("uq_knowledge_points_code", ["code"])
        batch.create_foreign_key(
            "fk_knowledge_points_import_batch_id",
            BATCH_TABLE,
            ["import_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_knowledge_points_difficulty",
            "difficulty IS NULL OR difficulty IN ('easy', 'medium', 'hard')",
        )
        batch.create_check_constraint(
            "ck_knowledge_points_estimated_minutes",
            "estimated_minutes IS NULL OR estimated_minutes >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table(KP_TABLE) as batch:
        batch.drop_constraint("ck_knowledge_points_estimated_minutes", type_="check")
        batch.drop_constraint("ck_knowledge_points_difficulty", type_="check")
        batch.drop_constraint("fk_knowledge_points_import_batch_id", type_="foreignkey")
        batch.drop_constraint("uq_knowledge_points_code", type_="unique")
    op.drop_index("ix_knowledge_points_import_batch_id", table_name=KP_TABLE)
    for column in reversed(KP_NEW_COLUMNS):
        op.drop_column(KP_TABLE, column)

    # 顺序不可交换：InnoDB 把 user_id 上的这个索引当作
    # fk_knowledge_point_import_batches_user_id 的支撑索引（实测
    # information_schema.statistics 中 user_id 只有这 1 个索引），
    # 若先 DROP INDEX 会直接报 MySQL 1553
    # 「Cannot drop index ... needed in a foreign key constraint」。
    with op.batch_alter_table(BATCH_TABLE) as batch:
        batch.drop_constraint(
            "fk_knowledge_point_import_batches_user_id", type_="foreignkey"
        )
    op.drop_index("ix_knowledge_point_import_batches_user_id", table_name=BATCH_TABLE)
    op.drop_table(BATCH_TABLE)
