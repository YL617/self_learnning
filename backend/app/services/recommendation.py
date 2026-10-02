"""今日学习建议引擎（推荐系统 V1）。

设计约束（与大阶段 2 的掌握度算法同构）：
  - **零训练、零 LLM**：全部为确定性规则 + 图统计 + 统计量，不调用任何模型。
  - **可解释**：每条建议都给出 `components`（打分分解）与模板化 `reason`，
    两者都来自真实数据，禁止编造。
  - **权重集中**：所有系数只在本模块常量区出现，禁止散落在 API route。
  - **只读**：本模块不写任何业务表；建议不自动落入 `PlanItem`。

打分：
    score = BASE[action]
          × urgency      （错题逾期越久越高，封顶）
          × gap          （掌握度越低越优先）
          × goal         （命中用户目标/计划则加权）
          × unlock       （学会它能解锁的下游知识点越多越高）
          × recency      （最近刚练过则降权，避免反复推同一个点）

V2（Knowledge Tracing）数据规模门禁也定义在本模块，未达标即拒绝：
    BKT 参数拟合：总作答 ≥ 5000 且 单知识点作答中位数 ≥ 30 且 用户 ≥ 50 且 知识点覆盖率 ≥ 80%
    深度 KT：总作答 ≥ 100000 且 用户 ≥ 1000
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AnswerRecord,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
    StudyPlan,
    UserProfile,
    WrongBookItem,
)
from app.services.knowledge_point_service import (
    KP_NODE_TYPE_CONCEPT,
    clean_name,
    normalize_subject,
)
from app.services.mastery import MASTERY_INITIAL, MASTERY_MAX, WEAK_THRESHOLD
from app.services.prerequisite import PrerequisiteService
from app.services.question_knowledge_point_service import QKP_ROLE_PRIMARY

# ---------------------------------------------------------------- 动作类型
ACTION_REVIEW_WRONG = "review_wrong"
ACTION_REVIEW_WEAK = "review_weak"
ACTION_LEARN_NEW = "learn_new"
ACTION_PRACTICE = "practice"
ACTIONS = (
    ACTION_REVIEW_WRONG,
    ACTION_REVIEW_WEAK,
    ACTION_LEARN_NEW,
    ACTION_PRACTICE,
)

ACTION_LABELS: dict[str, str] = {
    ACTION_REVIEW_WRONG: "复习错题",
    ACTION_REVIEW_WEAK: "巩固薄弱知识点",
    ACTION_LEARN_NEW: "学习新知识点",
    ACTION_PRACTICE: "加练",
}

# ---------------------------------------------------------------- 打分配置（唯一来源）
BASE_SCORES: dict[str, float] = {
    ACTION_REVIEW_WRONG: 100.0,
    ACTION_REVIEW_WEAK: 72.0,
    ACTION_LEARN_NEW: 52.0,
    ACTION_PRACTICE: 34.0,
}

GAP_WEIGHT = 0.6  # 掌握度缺口权重：越低分越优先
GOAL_BONUS = 0.25  # 命中用户目标/计划时的加成
UNLOCK_STEP = 0.12  # 每解锁 1 个下游知识点的加成
UNLOCK_CAP = 0.6  # 解锁加成封顶
RECENCY_DAYS = 3  # 最近 N 天内练过 → 降权
RECENCY_PENALTY = 0.6
OVERDUE_STEP = 0.15  # 每逾期 1 天的紧迫度加成
OVERDUE_CAP = 1.6

RECENT_ANSWER_WINDOW = 5  # reason 里"最近 N 次作答"的窗口
PRACTICE_MAX_ATTEMPTS = 2  # 作答次数少于该值且已达标 → 建议加练

ESTIMATED_MINUTES: dict[str, int] = {
    ACTION_REVIEW_WRONG: 15,
    ACTION_REVIEW_WEAK: 20,
    ACTION_LEARN_NEW: 30,
    ACTION_PRACTICE: 15,
}

DEFAULT_RECOMMENDATION_LIMIT = 3
MAX_RECOMMENDATION_LIMIT = 10
MAX_LINKED_QUESTION_IDS = 8

# ---------------------------------------------------------------- V2 门禁
V2_BKT_GATES: dict[str, float] = {
    "min_total_answers": 5_000,
    "min_median_kp_answers": 30,
    "min_users": 50,
    "min_kp_coverage": 0.8,
}
V2_DEEP_GATES: dict[str, float] = {
    "min_total_answers": 100_000,
    "min_users": 1_000,
}

_TOKEN_SPLIT = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


@dataclass(frozen=True)
class RecommendationItem:
    action: str
    knowledge_point_id: int
    knowledge_point_name: str
    subject: str
    score: float
    reason: str
    order: int
    estimated_minutes: int
    components: dict[str, float] = field(default_factory=dict)
    question_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class DataScaleSnapshot:
    total_answers: int
    user_count: int
    knowledge_point_count: int
    question_count: int
    tagged_question_count: int
    per_kp_answer_counts: tuple[int, ...]

    @property
    def kp_coverage(self) -> float:
        if self.question_count <= 0:
            return 0.0
        return self.tagged_question_count / self.question_count

    @property
    def median_kp_answers(self) -> float:
        if not self.per_kp_answer_counts:
            return 0.0
        return float(statistics.median(self.per_kp_answer_counts))


@dataclass(frozen=True)
class GateResult:
    name: str
    allowed: bool
    failed: tuple[str, ...]

    @property
    def threshold_snapshot(self) -> dict[str, float]:
        return dict(V2_BKT_GATES if self.name == "bkt" else V2_DEEP_GATES)


def _tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        token.lower()
        for token in _TOKEN_SPLIT.split(text)
        if len(token) >= 2
    }


def data_scale(db: Session) -> DataScaleSnapshot:
    """当前数据的规模快照（门禁与透明度用）。"""
    from app.models import User

    total_answers = int(db.scalar(select(func.count(AnswerRecord.id))) or 0)
    user_count = int(db.scalar(select(func.count(User.id))) or 0)
    # 只统计可学习知识点（concept）：目录节点不是学习对象，计入会让规模快照失真。
    knowledge_point_count = int(
        db.scalar(
            select(func.count(KnowledgePoint.id)).where(
                KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT
            )
        )
        or 0
    )
    question_count = int(db.scalar(select(func.count(Question.id))) or 0)
    tagged_question_count = int(
        db.scalar(
            select(func.count(func.distinct(QuestionKnowledgePoint.question_id)))
        )
        or 0
    )
    rows = db.execute(
        select(
            QuestionKnowledgePoint.knowledge_point_id,
            func.count(AnswerRecord.id),
        )
        .join(AnswerRecord, AnswerRecord.question_id == QuestionKnowledgePoint.question_id)
        .where(QuestionKnowledgePoint.role == QKP_ROLE_PRIMARY)
        .group_by(QuestionKnowledgePoint.knowledge_point_id)
    ).all()
    per_kp = tuple(sorted(int(count) for _, count in rows))
    return DataScaleSnapshot(
        total_answers=total_answers,
        user_count=user_count,
        knowledge_point_count=knowledge_point_count,
        question_count=question_count,
        tagged_question_count=tagged_question_count,
        per_kp_answer_counts=per_kp,
    )


def check_bkt_gate(snapshot: DataScaleSnapshot) -> GateResult:
    """V2-a：是否允许引入 BKT 参数拟合（未达标即拒绝）。"""
    failed: list[str] = []
    if snapshot.total_answers < V2_BKT_GATES["min_total_answers"]:
        failed.append(
            f"总作答 {snapshot.total_answers} < {V2_BKT_GATES['min_total_answers']:.0f}"
        )
    if snapshot.median_kp_answers < V2_BKT_GATES["min_median_kp_answers"]:
        failed.append(
            "单知识点作答中位数 "
            f"{snapshot.median_kp_answers:.1f} < {V2_BKT_GATES['min_median_kp_answers']:.0f}"
        )
    if snapshot.user_count < V2_BKT_GATES["min_users"]:
        failed.append(f"用户数 {snapshot.user_count} < {V2_BKT_GATES['min_users']:.0f}")
    if snapshot.kp_coverage < V2_BKT_GATES["min_kp_coverage"]:
        failed.append(
            f"知识点覆盖率 {snapshot.kp_coverage:.2f} < {V2_BKT_GATES['min_kp_coverage']:.2f}"
        )
    return GateResult("bkt", not failed, tuple(failed))


def check_deep_kt_gate(snapshot: DataScaleSnapshot) -> GateResult:
    """V2-c：是否允许引入深度 KT（DKT/SAKT/AKT 等）。"""
    failed: list[str] = []
    if snapshot.total_answers < V2_DEEP_GATES["min_total_answers"]:
        failed.append(
            f"总作答 {snapshot.total_answers} < {V2_DEEP_GATES['min_total_answers']:.0f}"
        )
    if snapshot.user_count < V2_DEEP_GATES["min_users"]:
        failed.append(f"用户数 {snapshot.user_count} < {V2_DEEP_GATES['min_users']:.0f}")
    return GateResult("deep_kt", not failed, tuple(failed))


MAX_CONTEXT_KNOWLEDGE_POINTS = 8
MAX_CONTEXT_WEAK_POINTS = 5


def learning_state_context(db: Session, user_id: int) -> dict[str, str]:
    """给「计划生成」用的真实学习状态文本。

    数值全部来自 `user_knowledge_point_mastery`，用于把中长期计划从
    「按专业和目标的模板化」变成「按学习状态的个性化」。没有数据就返回空字典，
    绝不编造掌握度。
    """
    from app.services.mastery import MasteryService

    service = MasteryService(db)
    rows = service.list_for_user(user_id)
    if not rows:
        return {}
    knowledge_points = service.knowledge_points_by_ids(
        [row.knowledge_point_id for row in rows]
    )
    knowledge_points.update(
        service.knowledge_points_by_ids(
            [row.knowledge_point_id for row in service.list_weak(user_id, limit=MAX_CONTEXT_WEAK_POINTS)]
        )
    )
    overview = [
        f"{knowledge_points[row.knowledge_point_id].name} {row.mastery_score}%"
        for row in rows[:MAX_CONTEXT_KNOWLEDGE_POINTS]
        if row.knowledge_point_id in knowledge_points
    ]
    context: dict[str, str] = {}
    if overview:
        context["mastery_summary"] = (
            f"已记录 {len(rows)} 个知识点，平均掌握度 "
            f"{round(service.average_score(user_id), 1)}%；" + "、".join(overview)
        )
    weak = [
        f"{knowledge_points[row.knowledge_point_id].name}（{row.mastery_score}%）"
        for row in service.list_weak(user_id, limit=MAX_CONTEXT_WEAK_POINTS)
        if row.knowledge_point_id in knowledge_points
    ]
    if weak:
        context["weak_points"] = "、".join(weak)
    return context


class RecommendationService:
    """今日建议引擎（只读）。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.prerequisites = PrerequisiteService(db)

    # ---------------------------------------------------------- 公开入口
    def today(
        self,
        user_id: int,
        *,
        limit: int = DEFAULT_RECOMMENDATION_LIMIT,
        today: date | None = None,
        now: datetime | None = None,
    ) -> list[RecommendationItem]:
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        anchor = today or date.today()
        bounded = max(1, min(int(limit), MAX_RECOMMENDATION_LIMIT))

        edges = self.prerequisites.edge_pairs()
        knowledge_points = self._knowledge_points()
        mastery_rows = self._mastery_rows(user_id)
        mastery_score = {row.knowledge_point_id: row.mastery_score for row in mastery_rows}
        linked_questions = self._linked_question_ids()
        goal_tokens = self._goal_tokens(user_id)
        recent_stats = self._recent_answer_stats(user_id)

        candidates: list[RecommendationItem] = []
        candidates.extend(
            self._review_wrong_candidates(
                user_id, anchor, knowledge_points, mastery_score, edges, goal_tokens,
                recent_stats, moment,
            )
        )
        candidates.extend(
            self._review_weak_candidates(
                mastery_rows, knowledge_points, mastery_score, edges, goal_tokens,
                recent_stats, linked_questions, moment,
            )
        )
        candidates.extend(
            self._learn_new_candidates(
                mastery_score, knowledge_points, edges, goal_tokens, linked_questions,
                moment,
            )
        )
        candidates.extend(
            self._practice_candidates(
                mastery_rows, knowledge_points, mastery_score, edges, goal_tokens,
                linked_questions, moment,
            )
        )

        # 同一知识点只保留得分最高的动作，避免"今天做同一件事三次"
        best: dict[int, RecommendationItem] = {}
        for item in candidates:
            current = best.get(item.knowledge_point_id)
            if current is None or item.score > current.score:
                best[item.knowledge_point_id] = item

        ordered = sorted(best.values(), key=lambda i: (-i.score, i.knowledge_point_id))
        return [
            RecommendationItem(
                action=item.action,
                knowledge_point_id=item.knowledge_point_id,
                knowledge_point_name=item.knowledge_point_name,
                subject=item.subject,
                score=item.score,
                reason=item.reason,
                order=index,
                estimated_minutes=item.estimated_minutes,
                components=item.components,
                question_ids=item.question_ids,
            )
            for index, item in enumerate(ordered[:bounded], start=1)
        ]

    # ---------------------------------------------------------- 数据装载
    def _knowledge_points(self) -> dict[int, KnowledgePoint]:
        """全部**可学习**知识点（active + concept）。

        这是 4 个动作（review_wrong / review_weak / learn_new / practice）共用的
        唯一候选装载函数：把 node_type 过滤放在这里，容器必然不会进入任何推荐动作。
        """
        rows = self.db.scalars(
            select(KnowledgePoint).where(
                KnowledgePoint.status == "active",
                KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT,
            )
        ).all()
        return {row.id: row for row in rows}

    def _mastery_rows(self, user_id: int):
        from app.services.mastery import MasteryService

        return MasteryService(self.db).list_for_user(user_id)

    def _linked_question_ids(self) -> dict[int, list[int]]:
        rows = self.db.execute(
            select(QuestionKnowledgePoint.knowledge_point_id, QuestionKnowledgePoint.question_id)
            .order_by(QuestionKnowledgePoint.question_id)
        ).all()
        mapping: dict[int, list[int]] = {}
        for knowledge_point_id, question_id in rows:
            bucket = mapping.setdefault(knowledge_point_id, [])
            if len(bucket) < MAX_LINKED_QUESTION_IDS:
                bucket.append(int(question_id))
        return mapping

    def _goal_tokens(self, user_id: int) -> set[str]:
        tokens: set[str] = set()
        profile = self.db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))
        if profile is not None:
            tokens |= _tokenize(profile.goals)
            tokens |= _tokenize(profile.weak_subjects)
            tokens |= _tokenize(profile.major)
        plans = self.db.scalars(
            select(StudyPlan).where(
                StudyPlan.user_id == user_id, StudyPlan.status == "active"
            )
        ).all()
        for plan in plans:
            tokens |= _tokenize(plan.title)
            tokens |= _tokenize(plan.goal)
            for item in plan.items:
                tokens |= _tokenize(item.subject)
                tokens |= _tokenize(item.title)
        return tokens

    def _recent_answer_stats(self, user_id: int) -> dict[int, tuple[int, int]]:
        """知识点 → (最近作答次数, 其中错题数)，只看 primary 关联。"""
        rows = self.db.execute(
            select(QuestionKnowledgePoint.knowledge_point_id, AnswerRecord.is_correct)
            .join(
                QuestionKnowledgePoint,
                QuestionKnowledgePoint.question_id == AnswerRecord.question_id,
            )
            .where(
                AnswerRecord.user_id == user_id,
                QuestionKnowledgePoint.role == QKP_ROLE_PRIMARY,
            )
            .order_by(AnswerRecord.created_at.desc(), AnswerRecord.id.desc())
        ).all()
        stats: dict[int, tuple[int, int]] = {}
        for knowledge_point_id, is_correct in rows:
            total, wrong = stats.get(int(knowledge_point_id), (0, 0))
            if total >= RECENT_ANSWER_WINDOW:
                continue
            stats[int(knowledge_point_id)] = (total + 1, wrong + (0 if is_correct else 1))
        return stats

    def _legacy_index(
        self, knowledge_points: dict[int, KnowledgePoint]
    ) -> dict[tuple[str, str], KnowledgePoint]:
        """legacy 题目只有自由文本知识点名；用它做一次确定性回退解析。

        入参来自 `_knowledge_points()`，因此天然只含 concept —— 容器名不会被用来
        回退解析题目文本（例如「排序」不会命中容器）。
        """
        index: dict[tuple[str, str], KnowledgePoint] = {}
        for knowledge_point in knowledge_points.values():
            key = (knowledge_point.normalized_subject, knowledge_point.normalized_name)
            index.setdefault(key, knowledge_point)
        return index

    # ---------------------------------------------------------- 打分
    def _score(
        self,
        *,
        action: str,
        mastery_score: int,
        unlock_count: int,
        goal_hit: bool,
        last_answered_at: datetime | None,
        now: datetime,
        urgency: float = 1.0,
    ) -> tuple[float, dict[str, float]]:
        gap_factor = 1.0 + GAP_WEIGHT * (MASTERY_MAX - mastery_score) / MASTERY_MAX
        goal_factor = 1.0 + GOAL_BONUS if goal_hit else 1.0
        unlock_factor = 1.0 + min(UNLOCK_STEP * unlock_count, UNLOCK_CAP)
        recent = False
        if last_answered_at is not None:
            stamp = last_answered_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            recent = (now - stamp) < timedelta(days=RECENCY_DAYS)
        recency_factor = RECENCY_PENALTY if recent else 1.0

        score = (
            BASE_SCORES[action]
            * urgency
            * gap_factor
            * goal_factor
            * unlock_factor
            * recency_factor
        )
        components = {
            "base": BASE_SCORES[action],
            "urgency": round(urgency, 4),
            "gap": round(gap_factor, 4),
            "goal": round(goal_factor, 4),
            "unlock": round(unlock_factor, 4),
            "recency": round(recency_factor, 4),
        }
        return round(score, 2), components

    @staticmethod
    def _goal_hit(knowledge_point: KnowledgePoint, tokens: set[str]) -> bool:
        if not tokens:
            return False
        name = knowledge_point.normalized_name
        subject = knowledge_point.normalized_subject
        for token in tokens:
            if name and (name in token or token in name):
                return True
            if subject and (subject in token or token in subject):
                return True
        return False

    @staticmethod
    def _goal_clause(goal_hit: bool) -> str:
        # 只陈述"与目标相关"这一事实，不编造具体目标内容。
        return "；命中你的学习目标或计划科目" if goal_hit else ""

    @staticmethod
    def _unlock_clause(unlock_count: int) -> str:
        return f"；学会它可以解锁 {unlock_count} 个后续知识点" if unlock_count > 0 else ""

    # ---------------------------------------------------------- 候选：复习错题
    def _review_wrong_candidates(
        self,
        user_id: int,
        today: date,
        knowledge_points: dict[int, KnowledgePoint],
        mastery_score: dict[int, int],
        edges: list[tuple[int, int]],
        goal_tokens: set[str],
        recent_stats: dict[int, tuple[int, int]],
        now: datetime,
    ) -> list[RecommendationItem]:
        due_items = self.db.scalars(
            select(WrongBookItem)
            .where(
                WrongBookItem.user_id == user_id,
                WrongBookItem.mastered.is_(False),
                WrongBookItem.next_review_date <= today,
            )
            .order_by(WrongBookItem.next_review_date)
        ).all()
        if not due_items:
            return []

        primary_kp = self._question_primary_kp_map(
            [item.question_id for item in due_items]
        )
        legacy = self._legacy_index(knowledge_points)

        grouped: dict[int, dict[str, object]] = {}
        for item in due_items:
            knowledge_point = primary_kp.get(item.question_id)
            if knowledge_point is None and item.question is not None:
                knowledge_point = legacy.get(
                    (
                        normalize_subject(item.question.subject),
                        clean_name(item.question.knowledge_point),
                    )
                )
            if knowledge_point is None:
                # 既没有结构化关联、也无法按名称回退 → 不猜、不硬塞。
                continue
            bucket = grouped.setdefault(
                knowledge_point.id, {"ids": [], "overdue": 0}
            )
            ids = bucket["ids"]
            assert isinstance(ids, list)
            if item.question_id not in ids:
                ids.append(item.question_id)
            overdue = (today - item.next_review_date).days
            bucket["overdue"] = max(int(bucket["overdue"]), max(overdue, 0))

        results: list[RecommendationItem] = []
        for knowledge_point_id, bucket in grouped.items():
            knowledge_point = knowledge_points.get(knowledge_point_id)
            if knowledge_point is None:
                continue
            ids = [int(i) for i in bucket["ids"]]  # type: ignore[union-attr]
            overdue_days = int(bucket["overdue"])  # type: ignore[arg-type]
            urgency = min(1.0 + OVERDUE_STEP * overdue_days, OVERDUE_CAP)
            unlock_count = self.prerequisites.unlock_count(
                knowledge_point_id, pairs=edges
            )
            goal_hit = self._goal_hit(knowledge_point, goal_tokens)
            score_now = mastery_score.get(knowledge_point_id, MASTERY_INITIAL)
            score, components = self._score(
                action=ACTION_REVIEW_WRONG,
                mastery_score=score_now,
                unlock_count=unlock_count,
                goal_hit=goal_hit,
                last_answered_at=None,
                now=now,
                urgency=urgency,
            )
            overdue_text = f"，最久逾期 {overdue_days} 天" if overdue_days > 0 else ""
            total, wrong = recent_stats.get(knowledge_point_id, (0, 0))
            recent_text = f"；最近 {total} 次作答错了 {wrong} 次" if total else ""
            parts = [
                f"{len(ids)} 道错题已到复习日{overdue_text}",
                f"掌握度 {score_now}%",
                recent_text.lstrip("；"),
                self._unlock_clause(unlock_count).lstrip("；"),
                self._goal_clause(goal_hit).lstrip("；"),
            ]
            results.append(
                RecommendationItem(
                    action=ACTION_REVIEW_WRONG,
                    knowledge_point_id=knowledge_point.id,
                    knowledge_point_name=knowledge_point.name,
                    subject=knowledge_point.subject,
                    score=score,
                    reason="；".join(part for part in parts if part),
                    order=0,
                    estimated_minutes=ESTIMATED_MINUTES[ACTION_REVIEW_WRONG],
                    components=components,
                    question_ids=tuple(ids),
                )
            )
        return results

    def _question_primary_kp_map(
        self, question_ids: list[int]
    ) -> dict[int, KnowledgePoint]:
        if not question_ids:
            return {}
        rows = self.db.execute(
            select(QuestionKnowledgePoint.question_id, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
            .where(
                QuestionKnowledgePoint.question_id.in_(set(question_ids)),
                QuestionKnowledgePoint.role == QKP_ROLE_PRIMARY,
                # 防御历史脏数据：即便曾把题目关联到容器，也不在推荐理由里带出容器名。
                KnowledgePoint.node_type == KP_NODE_TYPE_CONCEPT,
            )
        ).all()
        return {int(question_id): kp for question_id, kp in rows}

    # ---------------------------------------------------------- 候选：巩固薄弱点
    def _review_weak_candidates(
        self,
        mastery_rows,
        knowledge_points: dict[int, KnowledgePoint],
        mastery_score: dict[int, int],
        edges: list[tuple[int, int]],
        goal_tokens: set[str],
        recent_stats: dict[int, tuple[int, int]],
        linked_questions: dict[int, list[int]],
        now: datetime,
    ) -> list[RecommendationItem]:
        results: list[RecommendationItem] = []
        for row in mastery_rows:
            if row.attempt_count < 1 or row.mastery_score >= WEAK_THRESHOLD:
                continue
            knowledge_point = knowledge_points.get(row.knowledge_point_id)
            if knowledge_point is None:
                continue
            unlock_count = self.prerequisites.unlock_count(
                knowledge_point.id, pairs=edges
            )
            goal_hit = self._goal_hit(knowledge_point, goal_tokens)
            score, components = self._score(
                action=ACTION_REVIEW_WEAK,
                mastery_score=row.mastery_score,
                unlock_count=unlock_count,
                goal_hit=goal_hit,
                last_answered_at=row.last_answered_at,
                now=now,
            )
            total, wrong = recent_stats.get(knowledge_point.id, (0, 0))
            parts = [
                f"掌握度 {row.mastery_score}%，低于薄弱线 {WEAK_THRESHOLD}%",
                f"最近 {total} 次作答错了 {wrong} 次" if total else "",
                f"已作答 {row.attempt_count} 次" if row.attempt_count else "",
                self._unlock_clause(unlock_count).lstrip("；"),
                self._goal_clause(goal_hit).lstrip("；"),
            ]
            results.append(
                RecommendationItem(
                    action=ACTION_REVIEW_WEAK,
                    knowledge_point_id=knowledge_point.id,
                    knowledge_point_name=knowledge_point.name,
                    subject=knowledge_point.subject,
                    score=score,
                    reason="；".join(part for part in parts if part),
                    order=0,
                    estimated_minutes=ESTIMATED_MINUTES[ACTION_REVIEW_WEAK],
                    components=components,
                    question_ids=tuple(linked_questions.get(knowledge_point.id, [])),
                )
            )
        return results

    # ---------------------------------------------------------- 候选：学习新知识点
    def _learn_new_candidates(
        self,
        mastery_score: dict[int, int],
        knowledge_points: dict[int, KnowledgePoint],
        edges: list[tuple[int, int]],
        goal_tokens: set[str],
        linked_questions: dict[int, list[int]],
        now: datetime,
    ) -> list[RecommendationItem]:
        results: list[RecommendationItem] = []
        for knowledge_point_id, knowledge_point in sorted(knowledge_points.items()):
            if knowledge_point_id in mastery_score:
                continue  # 已作答过 → 不属于"新知识点"
            statuses = self.prerequisites.statuses_for(
                mastery_score, knowledge_point_id
            )
            if any(status.blocking for status in statuses):
                continue  # 硬前置未满足
            satisfied = [
                status for status in statuses if status.satisfied
            ]
            unlock_count = self.prerequisites.unlock_count(
                knowledge_point_id, pairs=edges
            )
            goal_hit = self._goal_hit(knowledge_point, goal_tokens)
            score, components = self._score(
                action=ACTION_LEARN_NEW,
                mastery_score=MASTERY_INITIAL,
                unlock_count=unlock_count,
                goal_hit=goal_hit,
                last_answered_at=None,
                now=now,
            )
            if satisfied:
                names = self.prerequisites.knowledge_points_by_ids(
                    [status.prerequisite_id for status in satisfied]
                )
                labels = "、".join(
                    f"「{names[status.prerequisite_id].name}」"
                    for status in satisfied
                    if status.prerequisite_id in names
                )
                lowest = min(
                    mastery_score.get(status.prerequisite_id, 0) for status in satisfied
                )
                reason = f"前置 {labels} 掌握度 {lowest}%，已满足开始条件"
            elif statuses:
                reason = "前置仅为建议强度（未设硬性门槛），可以先开始"
            else:
                reason = "没有前置知识点，可以直接开始"
            parts = [
                reason,
                self._unlock_clause(unlock_count).lstrip("；"),
                self._goal_clause(goal_hit).lstrip("；"),
            ]
            results.append(
                RecommendationItem(
                    action=ACTION_LEARN_NEW,
                    knowledge_point_id=knowledge_point.id,
                    knowledge_point_name=knowledge_point.name,
                    subject=knowledge_point.subject,
                    score=score,
                    reason="；".join(part for part in parts if part),
                    order=0,
                    estimated_minutes=ESTIMATED_MINUTES[ACTION_LEARN_NEW],
                    components=components,
                    question_ids=tuple(linked_questions.get(knowledge_point.id, [])),
                )
            )
        return results

    # ---------------------------------------------------------- 候选：加练
    def _practice_candidates(
        self,
        mastery_rows,
        knowledge_points: dict[int, KnowledgePoint],
        mastery_score: dict[int, int],
        edges: list[tuple[int, int]],
        goal_tokens: set[str],
        linked_questions: dict[int, list[int]],
        now: datetime,
    ) -> list[RecommendationItem]:
        results: list[RecommendationItem] = []
        for row in mastery_rows:
            if row.mastery_score < WEAK_THRESHOLD:
                continue  # 薄弱点走 review_weak
            if row.attempt_count >= PRACTICE_MAX_ATTEMPTS:
                continue
            knowledge_point = knowledge_points.get(row.knowledge_point_id)
            if knowledge_point is None:
                continue
            unlock_count = self.prerequisites.unlock_count(
                knowledge_point.id, pairs=edges
            )
            goal_hit = self._goal_hit(knowledge_point, goal_tokens)
            score, components = self._score(
                action=ACTION_PRACTICE,
                mastery_score=row.mastery_score,
                unlock_count=unlock_count,
                goal_hit=goal_hit,
                last_answered_at=row.last_answered_at,
                now=now,
            )
            parts = [
                f"已作答 {row.attempt_count} 次、掌握度 {row.mastery_score}%，再加练可以稳定",
                self._unlock_clause(unlock_count).lstrip("；"),
                self._goal_clause(goal_hit).lstrip("；"),
            ]
            results.append(
                RecommendationItem(
                    action=ACTION_PRACTICE,
                    knowledge_point_id=knowledge_point.id,
                    knowledge_point_name=knowledge_point.name,
                    subject=knowledge_point.subject,
                    score=score,
                    reason="；".join(part for part in parts if part),
                    order=0,
                    estimated_minutes=ESTIMATED_MINUTES[ACTION_PRACTICE],
                    components=components,
                    question_ids=tuple(linked_questions.get(knowledge_point.id, [])),
                )
            )
        return results


__all__ = [
    "ACTIONS",
    "ACTION_LABELS",
    "ACTION_LEARN_NEW",
    "ACTION_PRACTICE",
    "ACTION_REVIEW_WEAK",
    "ACTION_REVIEW_WRONG",
    "BASE_SCORES",
    "DEFAULT_RECOMMENDATION_LIMIT",
    "MAX_RECOMMENDATION_LIMIT",
    "V2_BKT_GATES",
    "V2_DEEP_GATES",
    "DataScaleSnapshot",
    "GateResult",
    "RecommendationItem",
    "RecommendationService",
    "check_bkt_gate",
    "check_deep_kt_gate",
    "data_scale",
    "learning_state_context",
]
