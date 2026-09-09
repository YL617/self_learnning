"""add missing core tables (courses, course_chapters) for fresh chain

Revision ID: 20260904_001
Revises: 20260829_002
Create Date: 2026-09-04
"""

import sqlalchemy as sa

from alembic import op

revision = "20260904_001"
down_revision = "20260829_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # courses 初始形态：后续 level/language/health_*/category 由 20260906/20260907 负责
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_courses_id", "courses", ["id"])

    op.create_table(
        "course_chapters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_course_chapters_id", "course_chapters", ["id"])
    op.create_index("ix_course_chapters_course_id", "course_chapters", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_course_chapters_course_id", table_name="course_chapters")
    op.drop_index("ix_course_chapters_id", table_name="course_chapters")
    op.drop_table("course_chapters")
    op.drop_index("ix_courses_id", table_name="courses")
    op.drop_table("courses")
