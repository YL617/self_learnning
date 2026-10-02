from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class KnowledgePointBrief(ORMModel):
    id: int
    name: str
    subject: str
    parent_id: int | None = None
    # 大阶段 4 P0：节点类型（缺省 None 保持向后兼容）。
    node_type: str | None = None
    # 大阶段 4 M1：可选展示字段（用于推荐与今日建议），默认 None 保持向后兼容。
    difficulty: str | None = None
    estimated_minutes: int | None = None


class MasteryOut(ORMModel):
    id: int
    knowledge_point_id: int
    mastery_score: int
    attempt_count: int
    correct_count: int
    correct_streak: int = 0
    last_answered_at: datetime | None = None
    last_correct_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    knowledge_point: KnowledgePointBrief | None = None


class MasterySummary(BaseModel):
    total: int
    weak_count: int
    average_score: float
    today_review_count: int
    weak_threshold: int
