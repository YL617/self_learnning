"""题目 ↔ 知识点结构化关联（Phase 2）。

不变量：
  - 每道题最多一个 role=primary；set_primary 是唯一显式切换入口。
  - 同一 (question, knowledge_point) 组合唯一；duplicate attach 幂等。
  - Question.subject 与 KnowledgePoint.subject 标准化后必须一致。
  - **只有 node_type=concept 的可学习知识点才能被关联**（container 一律拒绝）。
  - owner 之外一律 404 语义（由 Router 层传入 owner_id，None 表示管理员）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, Question, QuestionKnowledgePoint
from app.services.knowledge_point_service import (
    KP_NODE_TYPE_CONCEPT,
    normalize_subject,
)

QKP_ROLE_PRIMARY = "primary"
QKP_ROLE_SECONDARY = "secondary"

QKP_SOURCE_MANUAL = "manual"
QKP_SOURCE_AI = "ai"
QKP_SOURCE_LEGACY = "legacy"
QKP_SOURCE_SYSTEM = "system"


class QuestionKnowledgePointError(Exception):
    pass


class QuestionNotFound(QuestionKnowledgePointError):
    pass


class KnowledgePointNotFound(QuestionKnowledgePointError):
    pass


class NotLearnableNode(QuestionKnowledgePointError):
    """目录节点（node_type=container）不参与题目关联。"""




class AssociationNotFound(QuestionKnowledgePointError):
    pass


class SubjectMismatch(QuestionKnowledgePointError):
    pass


class PrimaryConflict(QuestionKnowledgePointError):
    pass


class QuestionKnowledgePointService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- 内部校验 ----

    def _get_question(self, question_id: int, owner_id: int | None) -> Question:
        statement = select(Question).where(Question.id == question_id)
        if owner_id is not None:
            statement = statement.where(Question.user_id == owner_id)
        question = self.db.scalar(statement)
        if question is None:
            raise QuestionNotFound("题目不存在")
        return question

    def _get_knowledge_point(self, knowledge_point_id: int) -> KnowledgePoint:
        """取知识点并强制「可学习」契约。

        这是「目录节点不产生 mastery」的**唯一可靠关口**：mastery 的唯一写入源是
        题目关联，关住关联即关住 mastery。任何未来的写入路径（含 M4 AI 标注接受）
        只要复用本服务，就自动被拦截，不依赖前端过滤。
        """
        item = self.db.get(KnowledgePoint, knowledge_point_id)
        if item is None:
            raise KnowledgePointNotFound("知识点不存在")
        if item.node_type != KP_NODE_TYPE_CONCEPT:
            raise NotLearnableNode("目录节点不能与题目关联")
        return item

    def _assert_subject(self, question: Question, knowledge_point: KnowledgePoint) -> None:
        if normalize_subject(question.subject) != knowledge_point.normalized_subject:
            raise SubjectMismatch("知识点与题目学科不一致")

    def _find_association(
        self, question_id: int, knowledge_point_id: int
    ) -> QuestionKnowledgePoint | None:
        return self.db.scalar(
            select(QuestionKnowledgePoint).where(
                QuestionKnowledgePoint.question_id == question_id,
                QuestionKnowledgePoint.knowledge_point_id == knowledge_point_id,
            )
        )

    def _assert_no_other_primary(
        self, question_id: int, exclude_knowledge_point_id: int | None = None
    ) -> None:
        statement = select(QuestionKnowledgePoint).where(
            QuestionKnowledgePoint.question_id == question_id,
            QuestionKnowledgePoint.role == QKP_ROLE_PRIMARY,
        )
        if exclude_knowledge_point_id is not None:
            statement = statement.where(
                QuestionKnowledgePoint.knowledge_point_id != exclude_knowledge_point_id
            )
        if self.db.scalar(statement) is not None:
            raise PrimaryConflict("该题目已存在主要知识点")

    # ---- 查询 ----

    def list_for_question(
        self, question_id: int, owner_id: int | None
    ) -> list[QuestionKnowledgePoint]:
        self._get_question(question_id, owner_id)
        statement = (
            select(QuestionKnowledgePoint)
            .where(QuestionKnowledgePoint.question_id == question_id)
            .order_by(QuestionKnowledgePoint.id)
        )
        return list(self.db.scalars(statement).all())

    def list_question_ids_for_knowledge_point(
        self, knowledge_point_id: int, owner_id: int | None
    ) -> list[int]:
        # 读取路径放宽：目录节点按契约不可能有题目，直接返回空列表，
        # 避免管理端遍历知识树时被 4xx 打断（不加"可学习"约束）。
        item = self.db.get(KnowledgePoint, knowledge_point_id)
        if item is None:
            raise KnowledgePointNotFound("知识点不存在")
        if item.node_type != KP_NODE_TYPE_CONCEPT:
            return []
        statement = (
            select(QuestionKnowledgePoint.question_id)
            .join(Question, Question.id == QuestionKnowledgePoint.question_id)
            .where(QuestionKnowledgePoint.knowledge_point_id == knowledge_point_id)
            .order_by(QuestionKnowledgePoint.id)
        )
        if owner_id is not None:
            statement = statement.where(Question.user_id == owner_id)
        return list(self.db.scalars(statement).all())

    # ---- 变更 ----

    def attach(
        self,
        question_id: int,
        knowledge_point_id: int,
        *,
        role: str = QKP_ROLE_PRIMARY,
        source: str = QKP_SOURCE_MANUAL,
        owner_id: int | None = None,
    ) -> QuestionKnowledgePoint:
        question = self._get_question(question_id, owner_id)
        knowledge_point = self._get_knowledge_point(knowledge_point_id)
        self._assert_subject(question, knowledge_point)

        existing = self._find_association(question_id, knowledge_point_id)
        if existing is not None:
            # 幂等：同一组合重复 attach 不改变状态；
            # 但若请求 primary 而题目已有另一个 primary，仍属冲突。
            if role == QKP_ROLE_PRIMARY and existing.role != QKP_ROLE_PRIMARY:
                self._assert_no_other_primary(question_id)
            return existing

        if role == QKP_ROLE_PRIMARY:
            self._assert_no_other_primary(question_id)
        item = QuestionKnowledgePoint(
            question_id=question_id,
            knowledge_point_id=knowledge_point_id,
            role=role,
            source=source,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def detach(
        self, question_id: int, knowledge_point_id: int, owner_id: int | None
    ) -> None:
        self._get_question(question_id, owner_id)
        item = self._find_association(question_id, knowledge_point_id)
        if item is None:
            raise AssociationNotFound("题目未关联该知识点")
        self.db.delete(item)
        self.db.flush()

    def replace(
        self,
        question_id: int,
        items: list[tuple[int, str]],
        *,
        source: str = QKP_SOURCE_MANUAL,
        owner_id: int | None = None,
    ) -> list[QuestionKnowledgePoint]:
        """全量替换题目关联；items 为 (knowledge_point_id, role) 列表。"""
        question = self._get_question(question_id, owner_id)

        seen: dict[int, str] = {}
        for knowledge_point_id, role in items:
            if knowledge_point_id in seen:
                raise QuestionKnowledgePointError("知识点不能重复提交")
            seen[knowledge_point_id] = role
        primary_count = sum(1 for role in seen.values() if role == QKP_ROLE_PRIMARY)
        if primary_count > 1:
            raise PrimaryConflict("最多只能有一个主要知识点")

        knowledge_points: dict[int, KnowledgePoint] = {}
        for knowledge_point_id in seen:
            knowledge_point = self._get_knowledge_point(knowledge_point_id)
            self._assert_subject(question, knowledge_point)
            knowledge_points[knowledge_point_id] = knowledge_point

        current = {
            row.knowledge_point_id: row
            for row in self.db.scalars(
                select(QuestionKnowledgePoint).where(
                    QuestionKnowledgePoint.question_id == question_id
                )
            ).all()
        }
        for knowledge_point_id in set(current) - set(seen):
            self.db.delete(current[knowledge_point_id])
        result: list[QuestionKnowledgePoint] = []
        for knowledge_point_id, role in seen.items():
            row = current.get(knowledge_point_id)
            if row is None:
                row = QuestionKnowledgePoint(
                    question_id=question_id,
                    knowledge_point_id=knowledge_point_id,
                    role=role,
                    source=source,
                )
                self.db.add(row)
            else:
                row.role = role
            result.append(row)
        self.db.flush()
        return sorted(result, key=lambda row: row.id)

    def set_primary(
        self, question_id: int, knowledge_point_id: int, owner_id: int | None
    ) -> QuestionKnowledgePoint:
        self._get_question(question_id, owner_id)
        item = self._find_association(question_id, knowledge_point_id)
        if item is None:
            raise AssociationNotFound("题目未关联该知识点")
        for row in self.db.scalars(
            select(QuestionKnowledgePoint).where(
                QuestionKnowledgePoint.question_id == question_id,
                QuestionKnowledgePoint.role == QKP_ROLE_PRIMARY,
            )
        ).all():
            row.role = QKP_ROLE_SECONDARY
        item.role = QKP_ROLE_PRIMARY
        self.db.flush()
        return item

    # ---- 出题兼容 ----

    def validate_knowledge_point_for_subject(
        self, knowledge_point_id: int, subject: str
    ) -> KnowledgePoint:
        """出题入口的前置校验：知识点存在且与请求学科一致。"""
        knowledge_point = self._get_knowledge_point(knowledge_point_id)
        if normalize_subject(subject) != knowledge_point.normalized_subject:
            raise SubjectMismatch("知识点与学科不一致")
        return knowledge_point
