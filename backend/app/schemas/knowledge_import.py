"""大阶段 4 M2：批量知识库导入的出入参模型。

这些模型是「导入管线」与「HTTP 层」之间唯一的契约；管线本身（
`app/services/knowledge_import.py`）只依赖这里的数据类，不依赖 FastAPI。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.mastery import KnowledgePointBrief

# 与 `knowledge_point_import_batches` 的 CHECK 约束一一对应（M1 已钉死）。
SourceFormat = Literal["tsv", "csv", "xlsx", "paste"]
ConflictStrategy = Literal["skip", "update_empty"]
BatchStatus = Literal["applied", "failed", "rolled_back"]

ImportIssueLevel = Literal["error", "warning"]
RowAction = Literal["create", "skip", "update_empty"]


class RowIssue(BaseModel):
    """一条校验结论（警告或错误）。

    `row` 为 `None` 表示整批级结论（B 系列）；行级结论使用 1-based 源行号。
    """

    row: int | None = None
    level: ImportIssueLevel
    code: str
    field: str | None = None
    message: str


class PreviewRow(BaseModel):
    row: int
    subject: str
    parent_path: str | None = None
    name: str
    code: str | None = None
    aliases: list[str] = Field(default_factory=list)
    difficulty: str | None = None
    estimated_minutes: int | None = None
    # 大阶段 4 P0：本行「知识点名」一律推导为 concept（目录由层级路径推导）。
    node_type: str = "concept"
    # 类型推导来源（让管理员在写库前看懂「为什么是这个类型」）。
    node_type_source: str | None = None
    action: RowAction = "create"
    # 命中既有知识点时给出其 id（`skip` / `update_empty` 才有值）。
    existing_kp_id: int | None = None
    issues: list[RowIssue] = Field(default_factory=list)


class PreviewNodeType(BaseModel):
    """预览中「将自动创建的目录节点」及其类型推导来源。"""

    name: str
    path: str
    node_type: str = "container"
    node_type_source: str = "由层级路径自动推导"


class ImportPreviewOut(BaseModel):
    """`preview` 的响应：解析事实 + 校验结论 + 执行计划（**不落库**）。"""

    source_format: SourceFormat
    detected_encoding: str | None = None
    detected_delimiter: str | None = None
    has_header: bool = True
    total_rows: int = 0
    error_rows: int = 0
    warning_rows: int = 0
    # 解析事实回显（编码回退 / 分隔符 / 空行剔除 / 多 sheet 等）。
    parse_notes: list[str] = Field(default_factory=list)
    # {"create": n, "skip": n, "update_empty": n, "create_parent": n,
    #  "create_concept": n, "create_container": n}
    # create_concept = 将创建的可学习知识点数；create_container = 将自动创建的目录节点数。
    # 刻意分成两个键，避免把「知识点」与「目录」混成一个 created_count。
    planned: dict[str, int] = Field(default_factory=dict)
    new_subjects: list[str] = Field(default_factory=list)
    parent_paths_to_create: list[str] = Field(default_factory=list)
    # 每个将自动创建的目录节点（名称 / 路径 / 类型 / 推导来源）。
    auto_parent_nodes: list[PreviewNodeType] = Field(default_factory=list)
    rows: list[PreviewRow] = Field(default_factory=list)
    truncated: bool = False
    conflict_strategy: ConflictStrategy = "skip"
    # = error_rows == 0（整批级问题会直接以 400/409 返回，不走到这里）。
    can_apply: bool = False


class ImportRejection(BaseModel):
    """400 / 409 的结构化错误体（作为 `HTTPException.detail` 返回）。

    用结构化 detail 而不是纯字符串，是为了让前端能直接渲染「哪些行错在哪」
    以及成环链路，而不必解析自然语言。
    """

    message: str
    code: str | None = None
    batch_errors: list[RowIssue] = Field(default_factory=list)
    row_issues: list[RowIssue] = Field(default_factory=list)
    cycle: list[str] = Field(default_factory=list)


class ImportApplyOut(BaseModel):
    """`apply` 的执行报告。"""

    batch_id: int
    status: Literal["applied", "failed"]
    source_format: str
    conflict_strategy: str
    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    # apply 成功时恒为 0（全有或全无）；失败时等于 total_rows。
    failed_count: int
    auto_parent_count: int
    # 显式双计数（P0）：新建可学习知识点数 / 自动创建目录节点数，不混成一个 created_count。
    created_concept_count: int = 0
    created_container_count: int = 0
    duration_ms: int
    rolled_back: bool = False
    rows: list[PreviewRow] = Field(default_factory=list)


class ImportBatchOut(ORMModel):
    """批次行（直接映射 `knowledge_point_import_batches`）。"""

    id: int
    user_id: int | None = None
    source_name: str | None = None
    source_format: str
    conflict_strategy: str
    status: str
    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    auto_parent_count: int
    error_summary: str | None = None
    created_at: datetime
    applied_at: datetime | None = None
    rolled_back_at: datetime | None = None


class BlockingRef(BaseModel):
    """阻止回滚的一条引用。"""

    knowledge_point_id: int
    knowledge_point_name: str
    reason: Literal[
        "has_children", "linked_question", "has_mastery", "prerequisite_edge"
    ]
    detail: str


class ImportBatchDetailOut(ImportBatchOut):
    """批次明细：本批可归属的知识点 + 回滚预检结果。"""

    knowledge_points: list[KnowledgePointBrief] = Field(default_factory=list)
    blocking_references: list[BlockingRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RollbackOut(BaseModel):
    batch_id: int
    deleted_count: int
    # `update_empty` 填充过、但回滚**不会**清空的条数（见设计方案 §8.3 的局限）。
    kept_updated_count: int
    status: Literal["rolled_back"]
    rolled_back_at: datetime
