from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.mastery import KnowledgePointBrief


class PrerequisiteCreate(BaseModel):
    """管理员添加前置边：prerequisite_id 必须在 knowledge_point_id 之前学。"""

    prerequisite_id: int = Field(ge=1)
    strength: int = Field(default=100, ge=0, le=100)
    note: str | None = Field(default=None, max_length=500)


class PrerequisiteRead(ORMModel):
    id: int
    knowledge_point_id: int
    prerequisite_id: int
    strength: int
    source: str
    status: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime
    prerequisite: KnowledgePointBrief | None = None
    # 针对当前请求用户：该前置是否已满足 / 是否构成阻塞
    satisfied: bool | None = None
    blocking: bool | None = None


class PrerequisiteDetailOut(BaseModel):
    knowledge_point: KnowledgePointBrief
    ready: bool
    threshold: int
    items: list[PrerequisiteRead]


class LearningPathStep(BaseModel):
    order: int
    knowledge_point: KnowledgePointBrief
    mastery_score: int | None = None
    satisfied: bool
    is_target: bool


class LearningPathOut(BaseModel):
    target: KnowledgePointBrief
    ready: bool
    threshold: int
    steps: list[LearningPathStep]


class PrerequisiteSuggestion(BaseModel):
    prerequisite_id: int
    prerequisite_name: str
    reason: str
    confidence: float


class PrerequisiteSuggestOut(BaseModel):
    knowledge_point: KnowledgePointBrief
    suggestions: list[PrerequisiteSuggestion]
    note: str | None = None
