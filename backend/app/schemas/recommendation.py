from typing import Literal

from pydantic import BaseModel

RecommendationAction = Literal["review_wrong", "review_weak", "learn_new", "practice"]


class RecommendationOut(BaseModel):
    action: RecommendationAction
    action_label: str
    knowledge_point_id: int
    knowledge_point_name: str
    subject: str
    score: float
    reason: str
    order: int
    estimated_minutes: int
    # 打分分解项：让"为什么推荐这个"可被人工核对，而不是黑箱
    components: dict[str, float] = {}
    question_ids: list[int] = []


class RecommendationTodayOut(BaseModel):
    date: str
    weak_threshold: int
    ready_threshold: int
    items: list[RecommendationOut]
