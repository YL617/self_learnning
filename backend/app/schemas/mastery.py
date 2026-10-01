from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class KnowledgePointBrief(ORMModel):
    id: int
    name: str
    subject: str
    parent_id: int | None = None


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
