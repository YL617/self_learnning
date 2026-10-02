from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel

# 难度词表：与 MasteryService.DIFFICULTY_WEIGHTS、plan_items.difficulty 同源。
# 全项目只允许这一套（三方一致性由 tests/test_schema_tools.py 断言）。
KnowledgePointDifficulty = Literal["easy", "medium", "hard"]

# 节点类型词表（大阶段 4 P0）：与 KnowledgePointService.KP_NODE_TYPES、
# DB ck_knowledge_points_node_type 同源。
KnowledgePointNodeType = Literal["container", "concept"]

ALIAS_MAX_ITEMS = 20
ALIAS_MAX_LENGTH = 100


def clean_alias_list(value: object) -> list[str] | None:
    """规范别名输入：去空白、丢弃空项、按原顺序去重，并校验单个长度与总数量。

    `None` 原样透传（「没有别名」与「清空别名」由调用方按 `model_fields_set`
    区分）。既非字符串也非数组的输入同样原样交回，由 Pydantic 的字段类型给出
    标准的 422，而不是在这里抛一个语义不对的异常。
    ORM 侧读回的是 JSON 解码后的 list，本函数幂等，可安全复用。
    """
    if value is None or not isinstance(value, (str, list, tuple)):
        return value  # type: ignore[return-value]  -- 交给字段类型校验
    if isinstance(value, str):
        value = [value]
    cleaned: list[str] = []
    for raw in value:
        text = str(raw).strip()
        if not text:
            continue
        if len(text) > ALIAS_MAX_LENGTH:
            raise ValueError(f"单个别名不能超过 {ALIAS_MAX_LENGTH} 个字符")
        if text not in cleaned:
            cleaned.append(text)
    if len(cleaned) > ALIAS_MAX_ITEMS:
        raise ValueError(f"别名最多 {ALIAS_MAX_ITEMS} 个")
    return cleaned


class KnowledgePointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    description: str | None = None
    status: Literal["active", "pending", "disabled"] = "active"
    source: Literal["system", "admin", "ai"] = "admin"
    # ---- 大阶段 4 P0：节点类型（缺省 concept，与 DB server_default 一致）----
    node_type: KnowledgePointNodeType = "concept"
    # ---- 大阶段 4 M1：知识库内容元数据（全部可选）----
    code: str | None = Field(default=None, max_length=64)
    aliases: list[str] | None = None
    difficulty: KnowledgePointDifficulty | None = None
    estimated_minutes: int | None = Field(default=None, ge=0, le=100_000)

    @field_validator("aliases", mode="before")
    @classmethod
    def _clean_aliases(cls, value: object) -> object:
        return clean_alias_list(value)


class KnowledgePointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = None
    description: str | None = None
    status: Literal["active", "pending", "disabled"] | None = None
    # 显式传 null 表示不修改类型（类型非空，不存在"清空"语义）。
    node_type: KnowledgePointNodeType | None = None
    # 显式传 null 表示清空该字段（服务层按 model_fields_set 判断）。
    code: str | None = Field(default=None, max_length=64)
    aliases: list[str] | None = None
    difficulty: KnowledgePointDifficulty | None = None
    estimated_minutes: int | None = Field(default=None, ge=0, le=100_000)

    @field_validator("aliases", mode="before")
    @classmethod
    def _clean_aliases(cls, value: object) -> object:
        return clean_alias_list(value)


class KnowledgePointRead(ORMModel):
    id: int
    name: str
    normalized_name: str
    subject: str
    parent_id: int | None = None
    description: str | None = None
    status: str
    source: str
    node_type: str
    code: str | None = None
    aliases: list[str] | None = None
    difficulty: str | None = None
    estimated_minutes: int | None = None
    import_batch_id: int | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgePointTreeNode(KnowledgePointRead):
    children: list["KnowledgePointTreeNode"] = Field(default_factory=list)
