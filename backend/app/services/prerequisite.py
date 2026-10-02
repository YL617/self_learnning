"""知识点前置依赖（prerequisite DAG）服务。

语义：一条 `(knowledge_point_id, prerequisite_id)` 边表示
「后者必须先学，才建议学前者」，即 `prerequisite_id` 在前、`knowledge_point_id` 在后。

与 `KnowledgePoint.parent_id` 严格分离：
  - `parent_id` 是归属层级（is-a / part-of，树，单父节点）；
  - 本模块是前置依赖（must-learn-before，多对多 DAG）。
树表达不了「C 同时依赖 A 和 B」，也表达不了「A 是 B 的父类但 B 不依赖 A」。

全部算法为确定性图统计：零训练、零 AI、可解释、可测试。
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, KnowledgePointPrerequisite
from app.services.knowledge_point_service import KP_NODE_TYPE_CONCEPT

# ---------------------------------------------------------------- 配置（唯一来源）
EDGE_STATUS_ACTIVE = "active"
EDGE_STATUS_DISABLED = "disabled"
EDGE_STATUSES = (EDGE_STATUS_ACTIVE, EDGE_STATUS_DISABLED)

EDGE_SOURCE_MANUAL = "manual"
EDGE_SOURCE_LLM = "llm"
EDGE_SOURCE_IMPORT = "import"
EDGE_SOURCES = (EDGE_SOURCE_MANUAL, EDGE_SOURCE_LLM, EDGE_SOURCE_IMPORT)

STRENGTH_MIN = 0
STRENGTH_MAX = 100
STRENGTH_DEFAULT = 100
# strength >= 该值算「硬前置」：未满足时阻止学习后置；低于该值只作学习顺序建议。
BLOCKING_STRENGTH = 60

# 前置被认为「已满足」所需的最低掌握度
READY_THRESHOLD = 70
# 从未作答（无掌握度记录）视为未满足；掌握度基线之上的"未知"不等于已掌握。
UNKNOWN_MASTERY = 0

# 防御性遍历上限：异常图也不允许让单次请求做无界遍历。
MAX_TRAVERSAL_NODES = 5000


class PrerequisiteError(Exception):
    pass


class KnowledgePointNotFound(PrerequisiteError):
    pass


class NotLearnableNode(PrerequisiteError):
    """目录节点（node_type=container）不能作为前置边的任一端点。"""




class SelfLoopPrerequisite(PrerequisiteError):
    pass


class PrerequisiteCycle(PrerequisiteError):
    pass


class DuplicatePrerequisite(PrerequisiteError):
    pass


class PrerequisiteLinkNotFound(PrerequisiteError):
    pass


@dataclass(frozen=True)
class PrerequisiteStatus:
    """单条前置关系对某个用户是否已满足。"""

    prerequisite_id: int
    strength: int
    satisfied: bool
    blocking: bool


def evaluate_statuses(
    edges: list[tuple[int, int]],
    mastery: dict[int, int],
    *,
    threshold: int = READY_THRESHOLD,
) -> list[PrerequisiteStatus]:
    """纯函数版满足度评估：`edges` 为 `(prerequisite_id, strength)` 序列。

    mastery 缺失（从未作答）视为未满足；`strength >= BLOCKING_STRENGTH` 才算硬前置。
    """
    statuses: list[PrerequisiteStatus] = []
    for prerequisite_id, strength in edges:
        satisfied = mastery.get(prerequisite_id, UNKNOWN_MASTERY) >= threshold
        statuses.append(
            PrerequisiteStatus(
                prerequisite_id=prerequisite_id,
                strength=strength,
                satisfied=satisfied,
                blocking=(not satisfied) and strength >= BLOCKING_STRENGTH,
            )
        )
    return statuses


class PrerequisiteService:
    """前置边读写 + DAG 算法。所有写入都在调用方事务内完成（只 flush）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ---------------------------------------------------------- 读取
    def list_for(
        self, knowledge_point_id: int, *, include_disabled: bool = False
    ) -> list[KnowledgePointPrerequisite]:
        """某知识点的前置列表（本点依赖谁）。"""
        statement = select(KnowledgePointPrerequisite).where(
            KnowledgePointPrerequisite.knowledge_point_id == knowledge_point_id
        )
        if not include_disabled:
            statement = statement.where(
                KnowledgePointPrerequisite.status == EDGE_STATUS_ACTIVE
            )
        statement = statement.order_by(
            KnowledgePointPrerequisite.strength.desc(),
            KnowledgePointPrerequisite.prerequisite_id,
        )
        return list(self.db.scalars(statement).all())

    def list_dependents(
        self, prerequisite_id: int, *, include_disabled: bool = False
    ) -> list[KnowledgePointPrerequisite]:
        """谁依赖了该知识点（反向查询）。"""
        statement = select(KnowledgePointPrerequisite).where(
            KnowledgePointPrerequisite.prerequisite_id == prerequisite_id
        )
        if not include_disabled:
            statement = statement.where(
                KnowledgePointPrerequisite.status == EDGE_STATUS_ACTIVE
            )
        statement = statement.order_by(KnowledgePointPrerequisite.knowledge_point_id)
        return list(self.db.scalars(statement).all())

    def get_edge(
        self, knowledge_point_id: int, prerequisite_id: int
    ) -> KnowledgePointPrerequisite | None:
        return self.db.scalar(
            select(KnowledgePointPrerequisite).where(
                KnowledgePointPrerequisite.knowledge_point_id == knowledge_point_id,
                KnowledgePointPrerequisite.prerequisite_id == prerequisite_id,
            )
        )

    def edge_pairs(self, *, include_disabled: bool = False) -> list[tuple[int, int]]:
        """全部边，返回 `(后置, 前置)` 二元组，按 id 稳定排序。"""
        statement = select(
            KnowledgePointPrerequisite.knowledge_point_id,
            KnowledgePointPrerequisite.prerequisite_id,
        )
        if not include_disabled:
            statement = statement.where(
                KnowledgePointPrerequisite.status == EDGE_STATUS_ACTIVE
            )
        statement = statement.order_by(
            KnowledgePointPrerequisite.knowledge_point_id,
            KnowledgePointPrerequisite.prerequisite_id,
        )
        return [(row[0], row[1]) for row in self.db.execute(statement).all()]

    def knowledge_points_by_ids(self, ids: list[int]) -> dict[int, KnowledgePoint]:
        if not ids:
            return {}
        rows = self.db.scalars(
            select(KnowledgePoint).where(KnowledgePoint.id.in_(set(ids)))
        ).all()
        return {row.id: row for row in rows}

    # ---------------------------------------------------------- 图算法
    @staticmethod
    def _reverse_index(pairs: list[tuple[int, int]]) -> dict[int, list[int]]:
        """前置 -> 后置列表（用它可以算「解锁」与可达性）。"""
        index: dict[int, list[int]] = defaultdict(list)
        for dependent, prerequisite in pairs:
            index[prerequisite].append(dependent)
        return index

    @staticmethod
    def _forward_index(pairs: list[tuple[int, int]]) -> dict[int, list[int]]:
        """后置 -> 前置列表（用它可以算「传递前置」与学习顺序）。"""
        index: dict[int, list[int]] = defaultdict(list)
        for dependent, prerequisite in pairs:
            index[dependent].append(prerequisite)
        return index

    def prerequisite_closure(
        self, knowledge_point_id: int, *, pairs: list[tuple[int, int]] | None = None
    ) -> set[int]:
        """传递前置集合（不含自身）。BFS 带 visited，成环也不会死循环。"""
        edges = self.edge_pairs() if pairs is None else pairs
        forward = self._forward_index(edges)
        seen: set[int] = set()
        queue: deque[int] = deque([knowledge_point_id])
        while queue and len(seen) < MAX_TRAVERSAL_NODES:
            node = queue.popleft()
            for prerequisite in forward.get(node, ()):
                if prerequisite not in seen:
                    seen.add(prerequisite)
                    queue.append(prerequisite)
        seen.discard(knowledge_point_id)
        return seen

    def unlock_count(
        self, knowledge_point_id: int, *, pairs: list[tuple[int, int]] | None = None
    ) -> int:
        """学会本知识点后，被解锁的后续知识点数量（传递后置计数）。"""
        edges = self.edge_pairs() if pairs is None else pairs
        reverse = self._reverse_index(edges)
        seen: set[int] = set()
        queue: deque[int] = deque([knowledge_point_id])
        while queue and len(seen) < MAX_TRAVERSAL_NODES:
            node = queue.popleft()
            for dependent in reverse.get(node, ()):
                if dependent not in seen:
                    seen.add(dependent)
                    queue.append(dependent)
        seen.discard(knowledge_point_id)
        return len(seen)

    def topological_order(
        self, node_ids: set[int], *, pairs: list[tuple[int, int]] | None = None
    ) -> list[int]:
        """对 `node_ids` 子图做确定性拓扑排序（前置在前，同层按 id 升序）。

        若子图意外含环（正常写入路径已拦截），把剩余节点按 id 追加，保证函数总是返回。
        """
        edges = self.edge_pairs() if pairs is None else pairs
        scoped = [(d, p) for d, p in edges if d in node_ids and p in node_ids]
        indegree = {node: 0 for node in node_ids}
        forward = self._forward_index(scoped)
        for dependent, _ in scoped:
            indegree[dependent] += 1
        ready = sorted(node for node, degree in indegree.items() if degree == 0)
        ordered: list[int] = []
        while ready:
            node = ready.pop(0)
            ordered.append(node)
            for dependent in sorted(forward.get(node, ())):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
            ready.sort()
        if len(ordered) < len(node_ids):
            ordered.extend(sorted(node_ids - set(ordered)))
        return ordered

    def learning_path(self, knowledge_point_id: int) -> list[KnowledgePoint]:
        """到目标知识点的前置学习路径（含目标本身，拓扑序）。"""
        pairs = self.edge_pairs()
        closure = self.prerequisite_closure(knowledge_point_id, pairs=pairs)
        nodes = closure | {knowledge_point_id}
        ordered = self.topological_order(nodes, pairs=pairs)
        mapping = self.knowledge_points_by_ids(ordered)
        return [mapping[node] for node in ordered if node in mapping]

    # ---------------------------------------------------------- 满足度
    def statuses_for(
        self,
        mastery: dict[int, int],
        knowledge_point_id: int,
        *,
        threshold: int = READY_THRESHOLD,
    ) -> list[PrerequisiteStatus]:
        """本知识点的每条前置是否已满足（mastery 缺失视为未满足）。"""
        edges = [
            (edge.prerequisite_id, edge.strength)
            for edge in self.list_for(knowledge_point_id)
        ]
        return evaluate_statuses(edges, mastery, threshold=threshold)

    def is_ready(
        self,
        mastery: dict[int, int],
        knowledge_point_id: int,
        *,
        threshold: int = READY_THRESHOLD,
    ) -> bool:
        """没有任何「硬前置未满足」时即可开始学习。"""
        return not any(
            status.blocking
            for status in self.statuses_for(
                mastery, knowledge_point_id, threshold=threshold
            )
        )

    # ---------------------------------------------------------- 写入
    def _assert_exists(self, knowledge_point_id: int, prerequisite_id: int) -> None:
        """校验两端存在，且**都必须是可学习知识点**（node_type=concept）。

        前置边的两端都是「能力」，不是「目录」。DB 无法表达这个约束（FK 指向同一张
        表），因此这里就是服务层的权威落点：container→concept / concept→container /
        container→container 一律拒绝。
        """
        dependent = self.db.get(KnowledgePoint, knowledge_point_id)
        if dependent is None:
            raise KnowledgePointNotFound("后置知识点不存在")
        prerequisite = self.db.get(KnowledgePoint, prerequisite_id)
        if prerequisite is None:
            raise KnowledgePointNotFound("前置知识点不存在")
        if dependent.node_type != KP_NODE_TYPE_CONCEPT:
            raise NotLearnableNode("目录节点不能作为前置关系的后置端点")
        if prerequisite.node_type != KP_NODE_TYPE_CONCEPT:
            raise NotLearnableNode("目录节点不能作为前置关系的端点")

    def would_create_cycle(self, knowledge_point_id: int, prerequisite_id: int) -> bool:
        """加入「prerequisite_id 在前、knowledge_point_id 在后」是否会成环。

        等价于：knowledge_point_id 已经是 prerequisite_id 的（传递）前置。
        """
        if knowledge_point_id == prerequisite_id:
            return True
        return knowledge_point_id in self.prerequisite_closure(prerequisite_id)

    def add(
        self,
        *,
        knowledge_point_id: int,
        prerequisite_id: int,
        strength: int = STRENGTH_DEFAULT,
        source: str = EDGE_SOURCE_MANUAL,
        note: str | None = None,
    ) -> KnowledgePointPrerequisite:
        # 先做「可学习知识点」身份闸门：container 端点一律在此被拒（含 container 自环），
        # 再判自环 / 重复 / 成环。这样目录节点无论以何种组合出现，报错都归因于类型而非结构。
        self._assert_exists(knowledge_point_id, prerequisite_id)
        if knowledge_point_id == prerequisite_id:
            raise SelfLoopPrerequisite("知识点不能作为自己的前置")
        if self.get_edge(knowledge_point_id, prerequisite_id) is not None:
            raise DuplicatePrerequisite("该前置关系已存在")
        if self.would_create_cycle(knowledge_point_id, prerequisite_id):
            raise PrerequisiteCycle("该前置关系会形成循环依赖，已拒绝")
        row = KnowledgePointPrerequisite(
            knowledge_point_id=knowledge_point_id,
            prerequisite_id=prerequisite_id,
            strength=min(max(int(strength), STRENGTH_MIN), STRENGTH_MAX),
            source=source if source in EDGE_SOURCES else EDGE_SOURCE_MANUAL,
            status=EDGE_STATUS_ACTIVE,
            note=note,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def remove(self, knowledge_point_id: int, prerequisite_id: int) -> None:
        edge = self.get_edge(knowledge_point_id, prerequisite_id)
        if edge is None:
            raise PrerequisiteLinkNotFound("前置关系不存在")
        self.db.delete(edge)
        self.db.flush()

    def has_edges(self, knowledge_point_id: int) -> bool:
        """该知识点是否被任何前置边引用（作为后置或前置）。删除预检用。"""
        statement = (
            select(KnowledgePointPrerequisite.id)
            .where(
                (KnowledgePointPrerequisite.knowledge_point_id == knowledge_point_id)
                | (KnowledgePointPrerequisite.prerequisite_id == knowledge_point_id)
            )
            .limit(1)
        )
        return self.db.scalar(statement) is not None


__all__ = [
    "BLOCKING_STRENGTH",
    "EDGE_SOURCE_IMPORT",
    "EDGE_SOURCE_LLM",
    "EDGE_SOURCE_MANUAL",
    "EDGE_STATUS_ACTIVE",
    "EDGE_STATUS_DISABLED",
    "READY_THRESHOLD",
    "STRENGTH_DEFAULT",
    "STRENGTH_MAX",
    "STRENGTH_MIN",
    "DuplicatePrerequisite",
    "KnowledgePointNotFound",
    "NotLearnableNode",
    "PrerequisiteCycle",
    "PrerequisiteError",
    "PrerequisiteLinkNotFound",
    "PrerequisiteService",
    "PrerequisiteStatus",
    "SelfLoopPrerequisite",
    "evaluate_statuses",
]
