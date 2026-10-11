"""M4 hotfix: tighten qkp kp_node_type CHECK to concept-only

Revision ID: 20261010_007
Revises: 20261010_006
Create Date: 2026-10-10

背景（20261010_006 上线后生产红线验证发现的缺口）：

006 引入的复合外键 ``(knowledge_point_id, kp_node_type) → knowledge_points(id,
node_type)`` 只能保证「(id, node_type) 对存在」；而 ``ck_qkp_kp_node_type`` 的
词表是 ``IN ('container', 'concept')``。于是显式写 ``kp_node_type='container'``
的裸 SQL 可以让 container 关联通过外键（container 行天然满足 (id,'container')），
「container 永不被题目关联」的 DB 级防线存在绕过路径。

本 revision 把 CHECK 收紧为 ``kp_node_type = 'concept'``：

  - 显式写 'container' → CHECK 拒绝；
  - 默认值/服务层恒写 'concept' 但目标是 container → 复合外键拒绝（006 既有防线）；
  - 两条路径闭合后，container 关联在数据库层被完全封堵。

存量数据风险为零：服务层恒写 'concept'，生产 qkp 为空表；CHECK 变更不触及
任何行的内容。SQLite 不支持 ALTER CHECK → 走 ``batch_alter_table``（MySQL 下
batch 直通为普通 ALTER TABLE DROP/ADD CHECK）。
"""

from alembic import op

revision = "20261010_007"
down_revision = "20261010_006"
branch_labels = None
depends_on = None

QKP_TABLE = "question_knowledge_points"
CHECK_NAME = "ck_qkp_kp_node_type"


def upgrade() -> None:
    with op.batch_alter_table(QKP_TABLE) as batch:
        batch.drop_constraint(CHECK_NAME, type_="check")
        batch.create_check_constraint(CHECK_NAME, "kp_node_type = 'concept'")


def downgrade() -> None:
    with op.batch_alter_table(QKP_TABLE) as batch:
        batch.drop_constraint(CHECK_NAME, type_="check")
        batch.create_check_constraint(
            CHECK_NAME, "kp_node_type IN ('container', 'concept')"
        )
