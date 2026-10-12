"""M5.5 P4-1: questions review lifecycle (review_status + audit trail)

Revision ID: 20261012_008
Revises: 20261010_007
Create Date: 2026-10-12

M5.5「学习数据激活」的 schema-only 变更（详见 docs/M5.5_学习数据激活设计方案.md §2/§3）。
采用 D1=B1「双轴」模型：``visibility``（可见范围 private/shared）语义与既有查询
**完全不动**，新增 ``review_status``（生命周期）承载审核门禁。对外可见的充要条件：

    对他人可见  ⇔  visibility = 'shared'  AND  review_status = 'approved'

变更内容（全部 additive，不修改任何既有列 / 约束 / 索引 / 表）：

  1. ``questions.review_status``：``VARCHAR(16) NOT NULL server_default 'draft'``
     + ``CHECK review_status IN ('draft','pending','approved','rejected','archived')``。
     存量 8 行自动落 ``draft``，且其 ``visibility='private'`` → 上述充要条件恒不成立，
     存量行为零变化（既不可见、也答不了的现状原样保持）。
  2. ``questions.reviewed_by``：``INTEGER NULL``，FK → ``users.id`` ``ondelete='SET NULL'``
     （审核人账号被删后题目保留、仅失去审核人指向）；独立索引
     ``ix_questions_reviewed_by``（同时被 MySQL 用作该 FK 的支撑索引，避免 InnoDB
     自动补一个同列索引导致 drift）。
  3. ``questions.reviewed_at``：``DATETIME NULL``（最近一次审核时间）。
  4. ``questions.review_note``：``TEXT NULL``（审核意见 / 驳回理由）。

顺序约定（沿 20261001_004 / 20261010_006 范式）：
  - SQLite 不支持 ``ALTER TABLE ADD CONSTRAINT`` → CHECK / FK 一律走
    ``batch_alter_table`` 重建（MySQL 下 batch 为直通，落地为普通 ALTER）。
  - **索引先建、外键后建**：InnoDB 会直接复用既有 ``ix_questions_reviewed_by``
    作为 FK 的支撑索引，不再自动补一个同列索引。
  - 本 revision 不新建表、不回填数据、不修改任何历史对象。

downgrade 与 upgrade 严格相反：先删 FK、再删 CHECK、再删索引，最后删 4 列
（InnoDB 下 FK 仍存活时 DROP INDEX 会报 1553，故 FK 必须先于索引消失）。
"""

import sqlalchemy as sa

from alembic import op

revision = "20261012_008"
down_revision = "20261010_007"
branch_labels = None
depends_on = None

QUESTION_TABLE = "questions"
REVIEW_STATUS_CHECK = "ck_questions_review_status"
REVIEWED_BY_FK = "fk_questions_reviewed_by"
REVIEWED_BY_INDEX = "ix_questions_reviewed_by"
NEW_COLUMNS = ("review_status", "reviewed_by", "reviewed_at", "review_note")


def upgrade() -> None:
    # ---- 1) 追加 4 列（review_status NOT NULL 带 server_default，存量行落 draft）----
    op.add_column(
        QUESTION_TABLE,
        sa.Column(
            "review_status",
            sa.String(length=16),
            nullable=False,
            server_default="draft",
        ),
    )
    op.add_column(
        QUESTION_TABLE,
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        QUESTION_TABLE,
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        QUESTION_TABLE,
        sa.Column("review_note", sa.Text(), nullable=True),
    )

    # ---- 2) 索引先建：MySQL 直接复用为 FK 支撑索引，不再自动补索引 ----
    op.create_index(REVIEWED_BY_INDEX, QUESTION_TABLE, ["reviewed_by"])

    # ---- 3) CHECK 与 FK：SQLite 走 batch 重建，MySQL 为直通 ALTER ----
    with op.batch_alter_table(QUESTION_TABLE) as batch:
        batch.create_check_constraint(
            REVIEW_STATUS_CHECK,
            "review_status IN ('draft', 'pending', 'approved', 'rejected', 'archived')",
        )
        batch.create_foreign_key(
            REVIEWED_BY_FK,
            "users",
            ["reviewed_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # 与 upgrade 严格相反：FK 必须先于其支撑索引消失（InnoDB 1553），
    # 再删索引，最后按追加的逆序删列。
    with op.batch_alter_table(QUESTION_TABLE) as batch:
        batch.drop_constraint(REVIEWED_BY_FK, type_="foreignkey")
        batch.drop_constraint(REVIEW_STATUS_CHECK, type_="check")
    op.drop_index(REVIEWED_BY_INDEX, table_name=QUESTION_TABLE)
    for column in reversed(NEW_COLUMNS):
        op.drop_column(QUESTION_TABLE, column)
