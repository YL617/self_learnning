from datetime import datetime

from sqlalchemy import (
    JSON,
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


class KnowledgePointImportBatch(Base):
    """知识点批量导入批次（大阶段 4 M1）。

    只承担两件事，且只有这两件：

      1. **追溯**：批次行记录「谁、什么时候、用哪种格式与冲突策略、导了多少」；
         被导入的知识点通过 `KnowledgePoint.import_batch_id` 反向归属到批次，
         因此批次表本身**不存放导入内容**。
      2. **回滚**：按批次反查 `import_batch_id` 即可定位该批次产生的全部知识点。

    `knowledge_points.import_batch_id` 的外键指向本表，所以同一 revision 内
    必须**先建本表、再加列**。

    计数列全部 NOT NULL + server_default '0'，避免「批次存在但读数缺失」的中间态。
    """

    __tablename__ = "knowledge_point_import_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applied', 'failed', 'rolled_back')",
            name="ck_knowledge_point_import_batches_status",
        ),
        CheckConstraint(
            "conflict_strategy IN ('skip', 'update_empty')",
            name="ck_knowledge_point_import_batches_conflict_strategy",
        ),
        CheckConstraint(
            "total_rows >= 0 AND created_count >= 0 AND updated_count >= 0 "
            "AND skipped_count >= 0 AND failed_count >= 0 AND auto_parent_count >= 0",
            name="ck_knowledge_point_import_batches_counts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # 操作人可被删除，但导入审计必须留存 → SET NULL，绝不 CASCADE。
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 文件名，或手工粘贴导入时的来源标签；仅作审计展示，不参与业务判断。
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_format: Mapped[str] = mapped_column(
        String(16), default="tsv", server_default="tsv"
    )
    conflict_strategy: Mapped[str] = mapped_column(
        String(16), default="skip", server_default="skip"
    )
    status: Mapped[str] = mapped_column(
        String(16), default="applied", server_default="applied"
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # 导入过程中自动创建的中间层级父节点数量（明细由导入报告逐行返回）。
    auto_parent_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class KnowledgePoint(Base):
    """全局共享知识点；知识点通过 normalized_name 做学科内去重。

    `node_type` 区分两类节点（大阶段 4 P0 修复）：
      - `container`：纯组织结构节点（目录），只参与层级与展示；
      - `concept`  ：真正可学习、可测试、可单独 mastery 的原子知识点。
    语义契约：container 不产生 mastery、不进推荐、不可题目关联、不作前置端点。
    """

    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint(
            "normalized_subject",
            "normalized_name",
            name="uq_knowledge_points_normalized_subject_name",
        ),
        # 稳定编码：改名/换学科不断链，也是导入幂等的对账键。可空 —— 两库的
        # UNIQUE 索引都允许多个 NULL，历史数据不必回填。
        UniqueConstraint("code", name="uq_knowledge_points_code"),
        # 难度词表与 plan_items.difficulty / MasteryService.DIFFICULTY_WEIGHTS 同源，
        # 全项目只允许这一套（大阶段 3 已因第二套难度语义踩过坑）。
        CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('easy', 'medium', 'hard')",
            name="ck_knowledge_points_difficulty",
        ),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes >= 0",
            name="ck_knowledge_points_estimated_minutes",
        ),
        # 节点类型词表钉死在 DB 层。`server_default='concept'` 是 fail-loud 原则：
        # 漏写类型 → 目录被当成知识点（可见错误）优于真知识点被静默降级（静默丢功能）。
        CheckConstraint(
            "node_type IN ('container', 'concept')",
            name="ck_knowledge_points_node_type",
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
    # ---- 大阶段 4 P0：节点类型（container | concept）----
    # NOT NULL + server_default `concept`：
    #   - 加列对存量行免回填；
    #   - 未来任何漏写 node_type 的 INSERT 也落为 concept（fail-loud，见类 docstring）。
    node_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="concept", server_default="concept", index=True
    )
    # ---- 大阶段 4 M1：知识库内容元数据 ----
    # 全部可空、无 server_default —— 加列对存量数据零风险，无需回填；
    # 生产实测该表 0 行，因此本次 ALTER 对线上是纯粹的空操作。
    #
    # 稳定编码（如 `DS.TREE.BST`）：改名/换学科不断链，也是导入幂等的对账键。
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 别名数组（如 `["堆栈", "stack"]`）。存在的唯一目的：防止同义名被建成多条
    # 知识点，从而把同一个知识点的掌握度拆散。用原生 JSON 而不是 JSON 文本，
    # 避免 `knowledge_point.aliases` 在业务代码里变成一个可直接迭代的字符串。
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # 仅用于展示、排序与推荐；**禁止参与 MasteryService 计算**（掌握度的难度
    # 系数来自作答记录，与本列无关）。
    difficulty: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # 预估学习时长（分钟），供推荐与今日建议展示。
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 导入批次归属；批次被删除时清空归属而不是连带删知识点。
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_point_import_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
