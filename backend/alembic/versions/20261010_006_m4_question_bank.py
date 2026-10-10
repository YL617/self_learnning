"""M4 question bank: questions difficulty/visibility + qkp concept-only composite FK

Revision ID: 20261010_006
Revises: 20261002_005
Create Date: 2026-10-10

M4 题库闭环的 schema-only 变更（详见 docs/M4设计方案.md §2）：

  1. ``questions.difficulty``：``VARCHAR(16) NULL``。可空——存量 8 行保持 NULL，
     ``evaluation.resolve_difficulty()`` 继续按题型映射（choice=easy / fill=medium /
     short_answer=hard），行为零变化；管理员建题时可显式指定（优先级已在代码预留）。
  2. ``questions.visibility``：``VARCHAR(16) NOT NULL server_default 'private'``。
     存量 8 行自动落为 ``private``（现状语义），行为零变化；``shared`` 供管理员
     共享题库（全部登录用户可见可做）。
  3. ``knowledge_points`` 加 ``UNIQUE (id, node_type)``：为复合外键提供引用目标。
  4. ``question_knowledge_points.kp_node_type``：``VARCHAR(16) NOT NULL
     server_default 'concept'`` + 复合外键 ``(knowledge_point_id, kp_node_type)``
     → ``knowledge_points (id, node_type)``。**这是 container 禁令的数据库级防线**：
     qkp 行必须命中 ``(id, 'concept')``，即使绕过服务层直接 INSERT container 关联
     也会被外键拒绝（此前只有 ``QuestionKnowledgePointService`` 应用层把关）。
     生产 qkp 当前 0 行，加列 + 约束是零风险操作。

顺序约定（沿 20261002_005 / 20261001_004 范式）：
  - SQLite 不支持 ``ALTER TABLE ADD CONSTRAINT`` → CHECK/UNIQUE/FK 全部走
    ``batch_alter_table``（MySQL 下 batch 是直通，落地为普通 ALTER）。
  - 先建 ``knowledge_points`` 的 UNIQUE，再建引用它的复合外键。
  - 本 revision 不新建表、不回填数据、不修改任何历史对象。

downgrade 与 upgrade 严格相反；无新增索引（复合外键可复用 qkp.knowledge_point_id
既有索引作为左前缀，InnoDB 不会再自动补索引）。
"""

import sqlalchemy as sa

from alembic import op

revision = "20261010_006"
down_revision = "20261002_005"
branch_labels = None
depends_on = None

QUESTION_TABLE = "questions"
KP_TABLE = "knowledge_points"
QKP_TABLE = "question_knowledge_points"


def upgrade() -> None:
    # 1) questions：难度（可空）+ 可见性（NOT NULL，存量行落 private）
    op.add_column(QUESTION_TABLE, sa.Column("difficulty", sa.String(length=16), nullable=True))
    op.add_column(
        QUESTION_TABLE,
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default="private",
        ),
    )
    with op.batch_alter_table(QUESTION_TABLE) as batch:
        batch.create_check_constraint(
            "ck_questions_difficulty",
            "difficulty IS NULL OR difficulty IN ('easy', 'medium', 'hard')",
        )
        batch.create_check_constraint(
            "ck_questions_visibility",
            "visibility IN ('private', 'shared')",
        )

    # 2) knowledge_points：UNIQUE(id, node_type) —— 复合外键的引用目标
    with op.batch_alter_table(KP_TABLE) as batch:
        batch.create_unique_constraint(
            "uq_knowledge_points_id_node_type",
            ["id", "node_type"],
        )

    # 3) question_knowledge_points：kp_node_type + 复合外键（DB 级 container 禁令）
    op.add_column(
        QKP_TABLE,
        sa.Column(
            "kp_node_type",
            sa.String(length=16),
            nullable=False,
            server_default="concept",
        ),
    )
    with op.batch_alter_table(QKP_TABLE) as batch:
        batch.create_check_constraint(
            "ck_qkp_kp_node_type",
            "kp_node_type IN ('container', 'concept')",
        )
        batch.create_foreign_key(
            "fk_qkp_kp_concept",
            KP_TABLE,
            ["knowledge_point_id", "kp_node_type"],
            ["id", "node_type"],
        )


def downgrade() -> None:
    # 与 upgrade 严格相反：先拆 qkp 复合外键与列，再拆 knowledge_points 唯一约束，
    # 最后拆 questions 两列（drop 外键必须先于任何依赖它的对象消失）。
    with op.batch_alter_table(QKP_TABLE) as batch:
        batch.drop_constraint("fk_qkp_kp_concept", type_="foreignkey")
        batch.drop_constraint("ck_qkp_kp_node_type", type_="check")
    op.drop_column(QKP_TABLE, "kp_node_type")

    with op.batch_alter_table(KP_TABLE) as batch:
        batch.drop_constraint("uq_knowledge_points_id_node_type", type_="unique")

    with op.batch_alter_table(QUESTION_TABLE) as batch:
        batch.drop_constraint("ck_questions_visibility", type_="check")
        batch.drop_constraint("ck_questions_difficulty", type_="check")
    op.drop_column(QUESTION_TABLE, "visibility")
    op.drop_column(QUESTION_TABLE, "difficulty")
