from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    KnowledgePoint,
    KnowledgePointPrerequisite,
    QuestionKnowledgePoint,
    UserKnowledgePointMastery,
)

KP_STATUS_ACTIVE = "active"
KP_STATUS_PENDING = "pending"
KP_STATUS_DISABLED = "disabled"

KP_SOURCE_SYSTEM = "system"
KP_SOURCE_ADMIN = "admin"
KP_SOURCE_AI = "ai"

# 节点类型词表（大阶段 4 P0 修复）。全项目只允许这一套，且由 DB
# `ck_knowledge_points_node_type` 钉死。三方一致性（本常量 / model CHECK /
# `KnowledgePointNodeType` schema）由 tests 断言。
#
#   container：纯组织结构节点（目录）。只作 parent、只参与层级与展示；
#              禁止进推荐 / mastery / 题目关联 / AI 标注 / 前置边端点 / 学习计划。
#   concept  ：真正可学习、可测试、可单独 mastery 的原子知识点。
KP_NODE_TYPE_CONTAINER = "container"
KP_NODE_TYPE_CONCEPT = "concept"
KP_NODE_TYPES: tuple[str, ...] = (KP_NODE_TYPE_CONTAINER, KP_NODE_TYPE_CONCEPT)

# 知识点难度词表（大阶段 4 M1）。全项目只允许这一套，且**只用于展示、排序与
# 推荐**——绝不参与掌握度计算（掌握度的难度系数来自作答记录，见
# MasteryService.DIFFICULTY_WEIGHTS，两者是不同来源的两个概念）。
#
# 这里刻意重复字面量而不 import mastery：knowledge_point_service ← mastery ←
# question_knowledge_point_service ← knowledge_point_service 会成环。
# 三方一致性（本常量 / DIFFICULTY_WEIGHTS / KnowledgePointDifficulty）由
# tests/test_schema_tools.py::test_knowledge_point_difficulty_vocabulary_is_pinned
# 与 tests/test_knowledge_point_profile_m1.py 断言。
KP_DIFFICULTY_LEVELS: tuple[str, ...] = ("easy", "medium", "hard")

CODE_MAX_LENGTH = 64

_WHITESPACE_RE = re.compile(r"\s+")


def _collapse_whitespace(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.replace("\u3000", " ").strip())


def clean_name(name: str) -> str:
    """去掉全角/半角空白并折叠连续空白，拉丁字母统一小写。"""
    return _collapse_whitespace(name).lower()


def clean_subject(subject: str) -> str:
    """对 subject 做同样的空白清洗，但保留原始大小写用于展示。"""
    return _collapse_whitespace(subject)


def normalize_subject(subject: str) -> str:
    """subject 的标准化形式，仅用于去重与比较，不用于展示。"""
    return clean_subject(subject).lower()


class KnowledgePointError(Exception):
    pass


class KnowledgePointNotFound(KnowledgePointError):
    pass


class DuplicateKnowledgePoint(KnowledgePointError):
    pass


class InvalidParent(KnowledgePointError):
    pass


class InvalidNodeType(KnowledgePointError):
    """节点类型约束被违反（例如把目录节点挂到可学习知识点之下）。"""


class ParentCycleError(KnowledgePointError):
    pass


class KnowledgePointHasChildren(KnowledgePointError):
    pass


class KnowledgePointInUse(KnowledgePointError):
    pass


class KnowledgePointService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, knowledge_point_id: int) -> KnowledgePoint | None:
        return self.db.get(KnowledgePoint, knowledge_point_id)

    def _get_or_raise(self, knowledge_point_id: int) -> KnowledgePoint:
        item = self.get(knowledge_point_id)
        if item is None:
            raise KnowledgePointNotFound("知识点不存在")
        return item

    def list_all(
        self,
        *,
        subject: str | None = None,
        parent_id: int | None = None,
        query: str | None = None,
        node_type: str | None = None,
    ) -> list[KnowledgePoint]:
        statement = select(KnowledgePoint)
        if subject is not None:
            statement = statement.where(
                KnowledgePoint.normalized_subject == normalize_subject(subject)
            )
        if parent_id is not None:
            statement = statement.where(KnowledgePoint.parent_id == parent_id)
        if query is not None:
            needle = clean_name(query)
            statement = statement.where(KnowledgePoint.normalized_name.contains(needle))
        if node_type is not None:
            statement = statement.where(KnowledgePoint.node_type == self._assert_node_type(node_type))
        statement = statement.order_by(KnowledgePoint.id)
        return list(self.db.scalars(statement).all())

    def list_children(self, parent_id: int) -> list[KnowledgePoint]:
        statement = (
            select(KnowledgePoint)
            .where(KnowledgePoint.parent_id == parent_id)
            .order_by(KnowledgePoint.id)
        )
        return list(self.db.scalars(statement).all())

    def subtree_ids(self, knowledge_point_id: int) -> list[int]:
        ids = [knowledge_point_id]
        frontier = [knowledge_point_id]
        while frontier:
            row = self.db.scalars(
                select(KnowledgePoint.id).where(KnowledgePoint.parent_id.in_(frontier))
            ).all()
            if not row:
                break
            ids.extend(row)
            frontier = list(row)
        return ids

    def get_subtree(self, knowledge_point_id: int) -> list[KnowledgePoint]:
        ids = self.subtree_ids(knowledge_point_id)
        if not ids:
            return []
        statement = select(KnowledgePoint).where(KnowledgePoint.id.in_(ids))
        return list(self.db.scalars(statement).all())

    def resolve_by_name(self, subject: str, name: str) -> KnowledgePoint | None:
        """Phase 1：标准化后精确查询；后续在此扩展别名/Embedding/AI 语义匹配。"""
        cleaned = clean_subject(subject)
        normalized = clean_name(name)
        if not cleaned or not normalized:
            return None
        statement = select(KnowledgePoint).where(
            KnowledgePoint.normalized_subject == normalize_subject(subject),
            KnowledgePoint.normalized_name == normalized,
        )
        return self.db.scalar(statement)

    def _assert_subject(self, subject: str) -> str:
        cleaned = clean_subject(subject)
        if not cleaned:
            raise ValueError("学科名称不能为空")
        return cleaned

    def _assert_name(self, name: str) -> str:
        cleaned = clean_name(name)
        if not cleaned:
            raise ValueError("知识点名称不能为空")
        return cleaned

    def _assert_unique(
        self,
        normalized_subject: str,
        normalized: str,
        exclude_id: int | None = None,
    ) -> None:
        statement = select(KnowledgePoint).where(
            KnowledgePoint.normalized_subject == normalized_subject,
            KnowledgePoint.normalized_name == normalized,
        )
        if exclude_id is not None:
            statement = statement.where(KnowledgePoint.id != exclude_id)
        if self.db.scalar(statement) is not None:
            raise DuplicateKnowledgePoint("同一学科下已存在相同知识点")

    def _assert_code(
        self, code: str | None, exclude_id: int | None = None
    ) -> str | None:
        """规范并校验稳定编码。

        大小写不敏感地判重：MySQL 默认排序规则本就大小写不敏感，SQLite 默认敏感，
        在服务层统一成「不敏感」可以让两个方言给出同样的行为（DB 唯一索引只兜底）。
        """
        if code is None:
            return None
        cleaned = _collapse_whitespace(code)
        if not cleaned:
            return None
        if len(cleaned) > CODE_MAX_LENGTH:
            raise ValueError(f"编码不能超过 {CODE_MAX_LENGTH} 个字符")
        statement = select(KnowledgePoint).where(
            func.lower(KnowledgePoint.code) == cleaned.lower()
        )
        if exclude_id is not None:
            statement = statement.where(KnowledgePoint.id != exclude_id)
        if self.db.scalar(statement) is not None:
            raise DuplicateKnowledgePoint("稳定编码已被其他知识点使用")
        return cleaned

    def _assert_difficulty(self, difficulty: str | None) -> str | None:
        if difficulty is None:
            return None
        if difficulty not in KP_DIFFICULTY_LEVELS:
            raise ValueError(f"难度只能是 {' / '.join(KP_DIFFICULTY_LEVELS)} 之一")
        return difficulty

    def _assert_estimated_minutes(self, minutes: int | None) -> int | None:
        if minutes is None:
            return None
        if minutes < 0:
            raise ValueError("预估学习时长不能为负数")
        return minutes

    def _assert_node_type(self, node_type: str | None) -> str:
        """规范并校验节点类型；缺省视为 `concept`（与 DB server_default 一致）。"""
        if node_type is None:
            return KP_NODE_TYPE_CONCEPT
        if node_type not in KP_NODE_TYPES:
            raise ValueError(f"节点类型只能是 {' / '.join(KP_NODE_TYPES)} 之一")
        return node_type

    def _assert_parent_child_types(
        self, *, parent: KnowledgePoint | None, child_type: str
    ) -> None:
        """父子类型约束：`container` 不得挂在 `concept` 之下。

        允许 parent→child：container→container / container→concept / concept→concept；
        禁止 concept→container（会产生 `concept └─ container └─ concept` 的语义混乱树）。
        服务层显式抛业务异常，不依赖 DB 的 IntegrityError。
        """
        if parent is None:
            return
        if (
            child_type == KP_NODE_TYPE_CONTAINER
            and parent.node_type == KP_NODE_TYPE_CONCEPT
        ):
            raise InvalidNodeType("目录节点不能挂在可学习知识点之下")

    def _assert_children_types(self, node_id: int, new_type: str) -> None:
        """把已有节点改为 `concept` 前，其下不得仍存在 `container` 子节点。"""
        if new_type != KP_NODE_TYPE_CONCEPT:
            return
        child = self.db.scalar(
            select(KnowledgePoint.id)
            .where(
                KnowledgePoint.parent_id == node_id,
                KnowledgePoint.node_type == KP_NODE_TYPE_CONTAINER,
            )
            .limit(1)
        )
        if child is not None:
            raise InvalidNodeType("该知识点之下仍有目录节点，不能改为可学习知识点")

    def _assert_parent(self, subject: str, parent_id: int) -> KnowledgePoint:
        parent = self.get(parent_id)
        if parent is None:
            raise InvalidParent("父知识点不存在")
        if parent.normalized_subject != normalize_subject(subject):
            raise InvalidParent("父知识点与子知识点必须属于同一学科")
        return parent

    def _assert_no_cycle(self, node_id: int, parent_id: int) -> None:
        current: int | None = parent_id
        seen: set[int] = set()
        while current is not None:
            if current == node_id:
                raise ParentCycleError("父知识点不能形成循环")
            if current in seen:
                break
            seen.add(current)
            parent = self.get(current)
            if parent is None:
                raise InvalidParent("父知识点不存在")
            current = parent.parent_id

    def create(
        self,
        *,
        name: str,
        subject: str,
        parent_id: int | None = None,
        description: str | None = None,
        status: str = KP_STATUS_ACTIVE,
        source: str = KP_SOURCE_ADMIN,
        code: str | None = None,
        aliases: list[str] | None = None,
        difficulty: str | None = None,
        estimated_minutes: int | None = None,
        import_batch_id: int | None = None,
        node_type: str | None = None,
    ) -> KnowledgePoint:
        cleaned_subject = self._assert_subject(subject)
        normalized_subject = normalize_subject(subject)
        normalized = self._assert_name(name)
        resolved_node_type = self._assert_node_type(node_type)
        self._assert_unique(normalized_subject, normalized)
        if parent_id is not None:
            parent = self._assert_parent(cleaned_subject, parent_id)
            self._assert_parent_child_types(parent=parent, child_type=resolved_node_type)
        item = KnowledgePoint(
            name=_collapse_whitespace(name),
            normalized_name=normalized,
            subject=cleaned_subject,
            normalized_subject=normalized_subject,
            parent_id=parent_id,
            description=description,
            status=status,
            source=source,
            node_type=resolved_node_type,
            code=self._assert_code(code),
            aliases=aliases or None,
            difficulty=self._assert_difficulty(difficulty),
            estimated_minutes=self._assert_estimated_minutes(estimated_minutes),
            import_batch_id=import_batch_id,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def update(
        self,
        knowledge_point_id: int,
        data: object,
    ) -> KnowledgePoint:
        item = self._get_or_raise(knowledge_point_id)
        fields = data.model_fields_set  # type: ignore[attr-defined]

        cleaned_subject = item.subject
        normalized_subject = item.normalized_subject
        if "subject" in fields and data.subject is not None:
            cleaned_subject = self._assert_subject(data.subject)
            normalized_subject = normalize_subject(data.subject)

        normalized: str | None = None
        if "name" in fields and data.name is not None:
            normalized = self._assert_name(data.name)
            self._assert_unique(normalized_subject, normalized, exclude_id=item.id)

        next_parent_id = item.parent_id
        if "parent_id" in fields:
            next_parent_id = data.parent_id

        next_node_type = item.node_type
        if "node_type" in fields and data.node_type is not None:
            next_node_type = self._assert_node_type(data.node_type)

        next_parent: KnowledgePoint | None = None
        if next_parent_id is not None:
            if next_parent_id == item.id:
                raise InvalidParent("知识点不能作为自己的父节点")
            next_parent = self._assert_parent(cleaned_subject, next_parent_id)
            self._assert_no_cycle(item.id, next_parent_id)
        elif item.parent_id is not None and cleaned_subject != item.subject:
            raise InvalidParent("存在父知识点时不能直接修改学科，请先解除父级")

        # 父子类型约束：container 不得挂在 concept 之下。
        self._assert_parent_child_types(parent=next_parent, child_type=next_node_type)
        # 改型为 concept 时，其下不得仍有 container 子节点。
        if next_node_type != item.node_type:
            self._assert_children_types(item.id, next_node_type)

        if "name" in fields and data.name is not None:
            item.name = _collapse_whitespace(data.name)
            item.normalized_name = normalized
        if "subject" in fields and data.subject is not None:
            item.subject = cleaned_subject
            item.normalized_subject = normalized_subject
        if "parent_id" in fields:
            item.parent_id = next_parent_id
        if "description" in fields:
            item.description = data.description
        if "status" in fields and data.status is not None:
            item.status = data.status
        if "node_type" in fields and data.node_type is not None:
            item.node_type = next_node_type
        # ---- 大阶段 4 M1：内容元数据（显式传 null 即清空）----
        if "code" in fields:
            item.code = self._assert_code(data.code, exclude_id=item.id)
        if "aliases" in fields:
            item.aliases = data.aliases or None
        if "difficulty" in fields:
            item.difficulty = self._assert_difficulty(data.difficulty)
        if "estimated_minutes" in fields:
            item.estimated_minutes = self._assert_estimated_minutes(data.estimated_minutes)
        return item

    def delete(self, knowledge_point_id: int) -> KnowledgePoint:
        item = self._get_or_raise(knowledge_point_id)
        has_children = self.db.scalar(
            select(KnowledgePoint.id)
            .where(KnowledgePoint.parent_id == knowledge_point_id)
            .limit(1)
        )
        if has_children is not None:
            raise KnowledgePointHasChildren("存在子知识点，无法删除")
        # Phase 2：存在题目关联时拒绝删除（DB RESTRICT 仅作最后防线）。
        linked_question = self.db.scalar(
            select(QuestionKnowledgePoint.id)
            .where(QuestionKnowledgePoint.knowledge_point_id == knowledge_point_id)
            .limit(1)
        )
        if linked_question is not None:
            raise KnowledgePointInUse("知识点已被题目关联，请先解除关联")
        # 大阶段 2：存在用户掌握度记录时同样拒绝，避免静默清空学习进度。
        has_mastery = self.db.scalar(
            select(UserKnowledgePointMastery.id)
            .where(UserKnowledgePointMastery.knowledge_point_id == knowledge_point_id)
            .limit(1)
        )
        if has_mastery is not None:
            raise KnowledgePointInUse("知识点已有用户掌握度记录，无法删除")
        # 大阶段 3：被前置依赖边引用时同样拒绝，避免破坏学习路径图。
        has_prerequisite_edge = self.db.scalar(
            select(KnowledgePointPrerequisite.id)
            .where(
                (KnowledgePointPrerequisite.knowledge_point_id == knowledge_point_id)
                | (KnowledgePointPrerequisite.prerequisite_id == knowledge_point_id)
            )
            .limit(1)
        )
        if has_prerequisite_edge is not None:
            raise KnowledgePointInUse("知识点已建立前置依赖关系，请先解除前置关系")
        self.db.delete(item)
        return item
