"""知识点掌握度（Mastery）确定性算法与读写服务。

设计要点：
  - mastery_score 恒为 0~100 的整数；算法完全确定、可解释、可测试，不调用 AI。
  - 输入只有 EvaluationResult（见 app.services.evaluation），因此未来接入编程判题
    （Judge0）等新题型时不需要重写掌握度系统。
  - 全部权重与系数集中在本模块常量，禁止散落在 API route 里。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, UserKnowledgePointMastery
from app.services.evaluation import (
    EvaluationResult,
    KnowledgePointSignal,
)
from app.services.knowledge_point_service import KP_NODE_TYPE_CONCEPT
from app.services.question_knowledge_point_service import (
    QKP_ROLE_PRIMARY,
    QKP_ROLE_SECONDARY,
)

# ---------------------------------------------------------------- 配置（唯一来源）
MASTERY_MIN = 0
MASTERY_MAX = 100
MASTERY_INITIAL = 50  # 第一次遇到知识点时的中性基线

# 难度权重：hard > medium > easy
DIFFICULTY_WEIGHTS: dict[str, float] = {"easy": 0.8, "medium": 1.0, "hard": 1.3}
# 角色权重：主知识点影响大于次知识点
ROLE_WEIGHTS: dict[str, float] = {
    QKP_ROLE_PRIMARY: 1.0,
    QKP_ROLE_SECONDARY: 0.5,
}
ROLE_WEIGHT_FALLBACK = 0.5

GAIN_BASE = 16.0  # 答对的基础增益
LOSS_BASE = 14.0  # 答错的基础降幅
HEADROOM_FLOOR = 0.35  # 余量缩放下限：越接近 0/100 变化越慢，避免一题爆表
STREAK_STEP = 1.5  # 连续答对每题追加
STREAK_CAP = 5  # 连续答对追加封顶
REVIEW_MULTIPLIER = 1.25  # 复习（错题重做）场景的增益系数

# 薄弱知识点判定：低于该分数且至少作答过一次
WEAK_THRESHOLD = 60
WEAK_MIN_ATTEMPTS = 1


def clamp(value: float) -> int:
    """把算法输出夹到 0~100 的整数区间。"""
    return int(max(MASTERY_MIN, min(MASTERY_MAX, round(value))))


def difficulty_weight(difficulty: str) -> float:
    return DIFFICULTY_WEIGHTS.get(difficulty, DIFFICULTY_WEIGHTS["medium"])


def role_weight(role: str) -> float:
    return ROLE_WEIGHTS.get(role, ROLE_WEIGHT_FALLBACK)


def compute_delta(
    current: int,
    *,
    correct: bool,
    difficulty: str = "medium",
    role: str = QKP_ROLE_PRIMARY,
    streak: int = 0,
    reviewed: bool = False,
) -> float:
    """计算一次评估对掌握度的增减量（可正可负）。

    - 答对：基础增益 × 难度权重 × 角色权重 × 复习系数 × 余量缩放 + 连续答对奖励
      余量缩放让分数越高时增幅越小，因此不可能一题直接到 100。
    - 答错：基础降幅 × 难度权重 × 角色权重 × 当前分数缩放（分数越低降得越少）。
    """
    weight = difficulty_weight(difficulty) * role_weight(role)
    if reviewed:
        weight *= REVIEW_MULTIPLIER

    if correct:
        headroom = (MASTERY_MAX - current) / MASTERY_MAX
        gain = GAIN_BASE * weight * (HEADROOM_FLOOR + (1 - HEADROOM_FLOOR) * headroom)
        if streak > 0:
            gain += min(STREAK_STEP * streak, STREAK_STEP * STREAK_CAP)
        return gain

    room = current / MASTERY_MAX
    return -(LOSS_BASE * weight * (HEADROOM_FLOOR + (1 - HEADROOM_FLOOR) * room))


def next_score(
    current: int,
    *,
    correct: bool,
    difficulty: str = "medium",
    role: str = QKP_ROLE_PRIMARY,
    streak: int = 0,
    reviewed: bool = False,
) -> int:
    return clamp(
        current
        + compute_delta(
            current,
            correct=correct,
            difficulty=difficulty,
            role=role,
            streak=streak,
            reviewed=reviewed,
        )
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MasteryService:
    """掌握度读写；所有变更都在调用方的事务内完成。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- 查询 ----

    def get(self, user_id: int, knowledge_point_id: int) -> UserKnowledgePointMastery | None:
        return self.db.scalar(
            select(UserKnowledgePointMastery).where(
                UserKnowledgePointMastery.user_id == user_id,
                UserKnowledgePointMastery.knowledge_point_id == knowledge_point_id,
            )
        )

    def list_for_user(self, user_id: int, *, limit: int | None = None) -> list[UserKnowledgePointMastery]:
        statement = (
            select(UserKnowledgePointMastery)
            .join(
                KnowledgePoint,
                KnowledgePoint.id == UserKnowledgePointMastery.knowledge_point_id,
            )
            .where(
                UserKnowledgePointMastery.user_id == user_id,
                # 读取层防御：container 永远不产生 mastery；即便历史脏数据存在，
                # 也不计入列表 / 统计（写入侧已由题目关联关口拦截）。
                KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT,
            )
            .order_by(
                UserKnowledgePointMastery.mastery_score.desc(),
                UserKnowledgePointMastery.id,
            )
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.db.scalars(statement).all())

    def list_weak(
        self,
        user_id: int,
        *,
        threshold: int = WEAK_THRESHOLD,
        limit: int = 10,
    ) -> list[UserKnowledgePointMastery]:
        statement = (
            select(UserKnowledgePointMastery)
            .join(
                KnowledgePoint,
                KnowledgePoint.id == UserKnowledgePointMastery.knowledge_point_id,
            )
            .where(
                UserKnowledgePointMastery.user_id == user_id,
                KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT,
                UserKnowledgePointMastery.attempt_count >= WEAK_MIN_ATTEMPTS,
                UserKnowledgePointMastery.mastery_score < threshold,
            )
            .order_by(
                UserKnowledgePointMastery.mastery_score.asc(),
                UserKnowledgePointMastery.attempt_count.desc(),
                UserKnowledgePointMastery.id,
            )
            .limit(max(1, limit))
        )
        return list(self.db.scalars(statement).all())

    def average_score(self, user_id: int) -> float:
        value = self.db.scalar(
            select(func.avg(UserKnowledgePointMastery.mastery_score))
            .join(
                KnowledgePoint,
                KnowledgePoint.id == UserKnowledgePointMastery.knowledge_point_id,
            )
            .where(
                UserKnowledgePointMastery.user_id == user_id,
                KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT,
            )
        )
        return float(value) if value is not None else 0.0

    def count_for_user(self, user_id: int) -> int:
        """该用户的有效掌握度记录数（只计 concept，用于 summary 的总数）。"""
        return int(
            self.db.scalar(
                select(func.count(UserKnowledgePointMastery.id))
                .join(
                    KnowledgePoint,
                    KnowledgePoint.id == UserKnowledgePointMastery.knowledge_point_id,
                )
                .where(
                    UserKnowledgePointMastery.user_id == user_id,
                    KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT,
                )
            )
            or 0
        )

    def count_weak(self, user_id: int, *, threshold: int = WEAK_THRESHOLD) -> int:
        """薄弱知识点数量（只计 concept）。"""
        return int(
            self.db.scalar(
                select(func.count(UserKnowledgePointMastery.id))
                .join(
                    KnowledgePoint,
                    KnowledgePoint.id == UserKnowledgePointMastery.knowledge_point_id,
                )
                .where(
                    UserKnowledgePointMastery.user_id == user_id,
                    KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT,
                    UserKnowledgePointMastery.attempt_count >= WEAK_MIN_ATTEMPTS,
                    UserKnowledgePointMastery.mastery_score < threshold,
                )
            )
            or 0
        )

    def knowledge_points_by_ids(self, ids: list[int]) -> dict[int, KnowledgePoint]:
        if not ids:
            return {}
        rows = self.db.scalars(
            select(KnowledgePoint).where(KnowledgePoint.id.in_(set(ids)))
        ).all()
        return {row.id: row for row in rows}

    # ---- 变更 ----

    def _get_or_create(self, user_id: int, signal: KnowledgePointSignal) -> UserKnowledgePointMastery:
        row = self.get(user_id, signal.knowledge_point_id)
        if row is None:
            row = UserKnowledgePointMastery(
                user_id=user_id,
                knowledge_point_id=signal.knowledge_point_id,
                mastery_score=MASTERY_INITIAL,
                attempt_count=0,
                correct_count=0,
                correct_streak=0,
            )
            self.db.add(row)
            self.db.flush()
        return row

    def apply_evaluation(
        self,
        user_id: int,
        result: EvaluationResult,
        *,
        reviewed: bool = False,
        now: datetime | None = None,
    ) -> list[UserKnowledgePointMastery]:
        """把一次评估结果落到所有关联知识点上（primary 权重大于 secondary）。

        调用方负责事务边界：本方法只 flush，不 commit。
        题目没有任何结构化知识点时返回空列表（legacy 题目行为不变）。
        """
        if not result.has_knowledge_points:
            return []

        moment = now or _now()
        updated: list[UserKnowledgePointMastery] = []
        for signal in result.knowledge_points:
            row = self._get_or_create(user_id, signal)
            row.mastery_score = next_score(
                row.mastery_score,
                correct=result.correct,
                difficulty=result.difficulty,
                role=signal.role,
                streak=row.correct_streak if result.correct else 0,
                reviewed=reviewed,
            )
            row.attempt_count += 1
            if result.correct:
                row.correct_count += 1
                row.correct_streak += 1
                row.last_correct_at = moment
            else:
                row.correct_streak = 0
            row.last_answered_at = moment
            if reviewed:
                row.last_reviewed_at = moment
            updated.append(row)
        self.db.flush()
        return updated


__all__ = [
    "DIFFICULTY_WEIGHTS",
    "GAIN_BASE",
    "LOSS_BASE",
    "MASTERY_INITIAL",
    "MASTERY_MAX",
    "MASTERY_MIN",
    "REVIEW_MULTIPLIER",
    "ROLE_WEIGHTS",
    "STREAK_CAP",
    "STREAK_STEP",
    "WEAK_THRESHOLD",
    "MasteryService",
    "clamp",
    "compute_delta",
    "difficulty_weight",
    "next_score",
    "role_weight",
]
