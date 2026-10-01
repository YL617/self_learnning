from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(32))
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    temp_cleanup_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    vector_id: Mapped[str | None] = mapped_column(String(128))


class FileAnalyzeResult(Base):
    __tablename__ = "file_analyze_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True, index=True
    )
    menu_json: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KnowledgePoint(Base):
    """全局共享知识点；知识点通过 normalized_name 做学科内去重。"""

    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint(
            "normalized_subject",
            "normalized_name",
            name="uq_knowledge_points_normalized_subject_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(100))
    normalized_subject: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    source: Mapped[str] = mapped_column(String(16), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    parent: Mapped["KnowledgePoint | None"] = relationship(
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[list["KnowledgePoint"]] = relationship(
        back_populates="parent",
    )


class KnowledgePointPrerequisite(Base):
    """知识点前置依赖边（大阶段 3）。

    语义：`knowledge_point_id` 依赖 `prerequisite_id`（必须先学会前置，才建议学后置）。

    与 `KnowledgePoint.parent_id` 严格区分：
      - `parent_id` 是「归属层级」（is-a / part-of，树，单父节点）；
      - 本表是「前置依赖」（must-learn-before，多对多 DAG）。
    二者不可互相替代，因此单独建边表，不改动 `parent_id` 语义。

    `strength` 0~100：>= 阻塞阈值视为硬前置（未满足则不建议学后置），
    低于阈值仅作为学习顺序建议。环与自环由 `PrerequisiteService` 与 DB CHECK 双重拦截。
    """

    __tablename__ = "knowledge_point_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_point_id",
            "prerequisite_id",
            name="uq_knowledge_point_prerequisites_pair",
        ),
        CheckConstraint(
            "knowledge_point_id <> prerequisite_id",
            name="ck_knowledge_point_prerequisites_no_self_loop",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_point_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT")
    )
    prerequisite_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="RESTRICT"), index=True
    )
    strength: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    source: Mapped[str] = mapped_column(
        String(16), default="manual", server_default="manual"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
