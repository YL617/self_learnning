from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgePoint

KP_STATUS_ACTIVE = "active"
KP_STATUS_PENDING = "pending"
KP_STATUS_DISABLED = "disabled"

KP_SOURCE_SYSTEM = "system"
KP_SOURCE_ADMIN = "admin"
KP_SOURCE_AI = "ai"

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


class ParentCycleError(KnowledgePointError):
    pass


class KnowledgePointHasChildren(KnowledgePointError):
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
    ) -> KnowledgePoint:
        cleaned_subject = self._assert_subject(subject)
        normalized_subject = normalize_subject(subject)
        normalized = self._assert_name(name)
        self._assert_unique(normalized_subject, normalized)
        if parent_id is not None:
            self._assert_parent(cleaned_subject, parent_id)
        item = KnowledgePoint(
            name=_collapse_whitespace(name),
            normalized_name=normalized,
            subject=cleaned_subject,
            normalized_subject=normalized_subject,
            parent_id=parent_id,
            description=description,
            status=status,
            source=source,
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

        if next_parent_id is not None:
            if next_parent_id == item.id:
                raise InvalidParent("知识点不能作为自己的父节点")
            self._assert_parent(cleaned_subject, next_parent_id)
            self._assert_no_cycle(item.id, next_parent_id)
        elif item.parent_id is not None and cleaned_subject != item.subject:
            raise InvalidParent("存在父知识点时不能直接修改学科，请先解除父级")

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
        self.db.delete(item)
        return item
