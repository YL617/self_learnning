"""统一学习评估结果（EvaluationResult）。

架构要点：掌握度（Mastery）只依赖本模块的 EvaluationResult，不依赖具体题型。
当前由 choice / fill / short_answer 产生；未来接入编程判题（Judge0）时，
只需把判题结果映射成同样的 EvaluationResult，掌握度系统无需重写。

确定性约束：difficulty / score 均由确定性规则推导，绝不调用 AI 决定。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Question, QuestionKnowledgePoint
from app.services.question_knowledge_point_service import (
    QKP_ROLE_PRIMARY,
    QKP_ROLE_SECONDARY,
)

# 第一版难度规则：题型 → 难度（可解释、可测试）。
# 若题库将来显式提供 difficulty 字段，resolve_difficulty 会优先采用。
DIFFICULTY_BY_QUESTION_TYPE: dict[str, str] = {
    "choice": "easy",
    "fill": "medium",
    "short_answer": "hard",
}
DIFFICULTY_FALLBACK = "medium"
VALID_DIFFICULTIES = ("easy", "medium", "hard")

# 答对时的评估得分（0~1）；答错恒为 0。
SCORE_CORRECT = 1.0
SCORE_INCORRECT = 0.0


@dataclass(frozen=True)
class KnowledgePointSignal:
    """一次评估需要影响的知识点及其角色。"""

    knowledge_point_id: int
    role: str = QKP_ROLE_PRIMARY

    @property
    def is_primary(self) -> bool:
        return self.role == QKP_ROLE_PRIMARY


@dataclass(frozen=True)
class EvaluationResult:
    """统一评估结果；所有学习状态更新都以它为唯一输入。"""

    question_id: int
    correct: bool
    score: float
    difficulty: str
    spent_seconds: int
    source_type: str
    knowledge_points: tuple[KnowledgePointSignal, ...] = field(default_factory=tuple)

    @property
    def has_knowledge_points(self) -> bool:
        return bool(self.knowledge_points)


def resolve_difficulty(question: Question) -> str:
    """确定性难度解析：显式 difficulty 优先，否则按题型映射。"""
    declared = getattr(question, "difficulty", None)
    if isinstance(declared, str) and declared in VALID_DIFFICULTIES:
        return declared
    return DIFFICULTY_BY_QUESTION_TYPE.get(question.question_type, DIFFICULTY_FALLBACK)


def load_knowledge_point_signals(
    db: Session, question_id: int
) -> tuple[KnowledgePointSignal, ...]:
    """读取题目的结构化知识点关联（role 决定权重来源）。"""
    rows = db.scalars(
        select(QuestionKnowledgePoint)
        .where(QuestionKnowledgePoint.question_id == question_id)
        .order_by(QuestionKnowledgePoint.id)
    ).all()
    return tuple(
        KnowledgePointSignal(
            knowledge_point_id=row.knowledge_point_id,
            role=row.role or QKP_ROLE_PRIMARY,
        )
        for row in rows
    )


def build_evaluation(
    question: Question,
    *,
    correct: bool,
    spent_seconds: int = 0,
    knowledge_points: tuple[KnowledgePointSignal, ...] = (),
) -> EvaluationResult:
    return EvaluationResult(
        question_id=question.id,
        correct=correct,
        score=SCORE_CORRECT if correct else SCORE_INCORRECT,
        difficulty=resolve_difficulty(question),
        spent_seconds=max(0, int(spent_seconds or 0)),
        source_type=question.question_type or "choice",
        knowledge_points=knowledge_points,
    )


__all__ = [
    "DIFFICULTY_BY_QUESTION_TYPE",
    "DIFFICULTY_FALLBACK",
    "QKP_ROLE_PRIMARY",
    "QKP_ROLE_SECONDARY",
    "VALID_DIFFICULTIES",
    "EvaluationResult",
    "KnowledgePointSignal",
    "build_evaluation",
    "load_knowledge_point_signals",
    "resolve_difficulty",
]
