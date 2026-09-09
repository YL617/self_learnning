"""schema reconciliation: close create_all-only objects

Revision ID: 20260909_001
Revises: 20260908_001
Create Date: 2026-09-09
"""

import sqlalchemy as sa

from alembic import op

revision = "20260909_001"
down_revision = "20260908_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 无历史迁移来源的整表
    op.create_table(
        "todos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_todos_id", "todos", ["id"])
    op.create_index("ix_todos_user_id", "todos", ["user_id"])
    op.create_index("ix_todos_due_date", "todos", ["due_date"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("remind_at", sa.DateTime(), nullable=False),
        sa.Column("triggered", sa.Boolean(), nullable=False),
        sa.Column("dismissed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reminders_id", "reminders", ["id"])
    op.create_index("ix_reminders_user_id", "reminders", ["user_id"])
    op.create_index("ix_reminders_remind_at", "reminders", ["remind_at"])

    op.create_table(
        "shop_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("effect_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_shop_items_name"),
    )
    op.create_index("ix_shop_items_id", "shop_items", ["id"])

    op.create_table(
        "plan_adjustment_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("study_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_adjustment_logs_id", "plan_adjustment_logs", ["id"])
    op.create_index("ix_plan_adjustment_logs_plan_id", "plan_adjustment_logs", ["plan_id"])

    op.create_table(
        "file_analyze_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("menu_json", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_analyze_results_id", "file_analyze_results", ["id"])
    op.create_index("ix_file_analyze_results_document_id", "file_analyze_results", ["document_id"], unique=True)

    # 无历史迁移来源的字段（server_default 为 SQLite/MySQL 加非空列所需；ORM 使用 Python-side default）
    op.add_column("plan_items", sa.Column("difficulty", sa.String(length=32), nullable=False, server_default="medium"))
    op.add_column("plan_items", sa.Column("suggested_time_slot", sa.String(length=64), nullable=True))
    op.add_column("plan_items", sa.Column("buffer_minutes", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("questions", sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    op.add_column("wrong_book_items", sa.Column("review_stage", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("wrong_book_items", sa.Column("next_review_date", sa.Date(), nullable=False, server_default=sa.text("'1970-01-01'")))
    op.add_column("wrong_book_items", sa.Column("last_reviewed_at", sa.DateTime(), nullable=True))

    op.add_column("documents", sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("temp_cleanup_at", sa.DateTime(), nullable=True))

    op.add_column("pets", sa.Column("hunger", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("pets", sa.Column("evolution_stage", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("pets", sa.Column("runaway", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("pets", sa.Column("hunger_updated_at", sa.DateTime(), nullable=True))
    op.add_column("pets", sa.Column("last_fed_at", sa.DateTime(), nullable=True))

    op.add_column("users", sa.Column("checkin_streak", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("last_checkin_date", sa.Date(), nullable=True))

    # 迁移漏建的索引：course_recommendations.status
    op.create_index("ix_course_recommendations_status", "course_recommendations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_course_recommendations_status", table_name="course_recommendations")

    op.drop_column("users", "last_checkin_date")
    op.drop_column("users", "checkin_streak")
    op.drop_column("pets", "last_fed_at")
    op.drop_column("pets", "hunger_updated_at")
    op.drop_column("pets", "runaway")
    op.drop_column("pets", "evolution_stage")
    op.drop_column("pets", "hunger")
    op.drop_column("documents", "temp_cleanup_at")
    op.drop_column("documents", "size_bytes")
    op.drop_column("wrong_book_items", "last_reviewed_at")
    op.drop_column("wrong_book_items", "next_review_date")
    op.drop_column("wrong_book_items", "review_stage")
    op.drop_column("questions", "is_favorite")
    op.drop_column("plan_items", "buffer_minutes")
    op.drop_column("plan_items", "suggested_time_slot")
    op.drop_column("plan_items", "difficulty")

    op.drop_index("ix_file_analyze_results_document_id", table_name="file_analyze_results")
    op.drop_index("ix_file_analyze_results_id", table_name="file_analyze_results")
    op.drop_table("file_analyze_results")
    op.drop_index("ix_plan_adjustment_logs_plan_id", table_name="plan_adjustment_logs")
    op.drop_index("ix_plan_adjustment_logs_id", table_name="plan_adjustment_logs")
    op.drop_table("plan_adjustment_logs")
    op.drop_index("ix_shop_items_id", table_name="shop_items")
    op.drop_table("shop_items")
    op.drop_index("ix_reminders_remind_at", table_name="reminders")
    op.drop_index("ix_reminders_user_id", table_name="reminders")
    op.drop_index("ix_reminders_id", table_name="reminders")
    op.drop_table("reminders")
    op.drop_index("ix_todos_due_date", table_name="todos")
    op.drop_index("ix_todos_user_id", table_name="todos")
    op.drop_index("ix_todos_id", table_name="todos")
    op.drop_table("todos")
