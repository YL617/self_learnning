"""题目审核生命周期状态机（M5.5 P4-2）。

双轴模型（D1=B1）：
  - ``visibility``（可见范围：private/shared）语义与他处查询**完全不动**；
  - ``review_status``（生命周期）承载审核门禁。

**对他人可见的充要条件 = ``visibility='shared' AND review_status='approved'``。**

状态机::

        ┌──────────────────────────────────────────────────────────┐
        │                                                          │
     [draft] ──submit_review──▶ [pending] ──approve──▶ [approved] ──publish──▶ (shared)
        ▲                         │                       │
        │                      reject                  archive
        │                         ▼                       ▼
        └────── edit ────────  [rejected]             [archived]

不变量（本服务的唯一职责边界）：
  - **状态转移是唯一入口**：非法转移一律 ``IllegalTransition``（Router 映射 409）。
  - **``visibility`` 只能经 ``publish`` 置为 ``shared``**；编辑接口永不触碰它。
  - **仅 ``draft``/``rejected`` 可编辑题干答案**；pending/approved/archived 只读。
  - ``archived`` 为终态（保留追溯，不再进入共享池，也无出边）。
  - ``reviewed_by``/``reviewed_at``/``review_note`` 记录**最近一次审核动作**
    （approve 清空旧 note；reject 写入新 note）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Question

# ---- review_status 词表（与 ck_questions_review_status 严格一致）----
REVIEW_STATUS_DRAFT = "draft"
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_ARCHIVED = "archived"

# ---- visibility 词表（与 ck_questions_visibility 严格一致）----
VISIBILITY_PRIVATE = "private"
VISIBILITY_SHARED = "shared"

# 仅这两个状态允许编辑题干/答案等（pending/approved/archived 一律只读）。
EDITABLE_REVIEW_STATUSES = frozenset({REVIEW_STATUS_DRAFT, REVIEW_STATUS_REJECTED})

# action -> (允许的来源状态集合, 目标状态)
_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "submit_review": (
        frozenset({REVIEW_STATUS_DRAFT, REVIEW_STATUS_REJECTED}),
        REVIEW_STATUS_PENDING,
    ),
    "approve": (frozenset({REVIEW_STATUS_PENDING}), REVIEW_STATUS_APPROVED),
    "reject": (frozenset({REVIEW_STATUS_PENDING}), REVIEW_STATUS_REJECTED),
    "archive": (frozenset({REVIEW_STATUS_APPROVED}), REVIEW_STATUS_ARCHIVED),
}

# 编辑接口允许改动的题面字段（visibility 永不在此列）。
EDITABLE_FIELDS = frozenset({"stem", "options", "answer", "analysis", "difficulty"})


class QuestionReviewError(Exception):
    """审核域错误基类。"""


class QuestionReviewNotFound(QuestionReviewError):
    pass


class IllegalTransition(QuestionReviewError):
    """当前状态不允许该动作（Router → 409）。"""


class QuestionNotEditable(QuestionReviewError):
    """非 draft/rejected 状态的题目不可编辑（Router → 409）。"""


def _now() -> datetime:
    # 列类型为朴素 DateTime；统一写朴素 UTC，与 admin 模块既有写法一致。
    return datetime.now(timezone.utc).replace(tzinfo=None)


class QuestionReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- 内部 ----

    def _get(self, question_id: int) -> Question:
        question = self.db.get(Question, question_id)
        if question is None:
            raise QuestionReviewNotFound("题目不存在")
        return question

    def _apply_transition(self, question: Question, action: str) -> Question:
        allowed, target = _TRANSITIONS[action]
        if question.review_status not in allowed:
            raise IllegalTransition(
                f"当前状态 {question.review_status} 不允许执行 {action}"
            )
        question.review_status = target
        return question

    # ---- 状态转移（离散端点，逐动作鉴权/留痕）----

    def submit_review(self, question_id: int) -> Question:
        """draft|rejected → pending。"""
        question = self._get(question_id)
        self._apply_transition(question, "submit_review")
        self.db.flush()
        return question

    def approve(self, question_id: int, reviewer_id: int) -> Question:
        """pending → approved（记录审核人与时间，清空历史驳回意见）。"""
        question = self._get(question_id)
        self._apply_transition(question, "approve")
        question.reviewed_by = reviewer_id
        question.reviewed_at = _now()
        question.review_note = None
        self.db.flush()
        return question

    def reject(self, question_id: int, reviewer_id: int, note: str | None = None) -> Question:
        """pending → rejected（记录审核人/时间/驳回意见）。"""
        question = self._get(question_id)
        self._apply_transition(question, "reject")
        question.reviewed_by = reviewer_id
        question.reviewed_at = _now()
        question.review_note = note
        self.db.flush()
        return question

    def publish(self, question_id: int) -> Question:
        """approved → shared（**visibility 置 shared 的唯一入口**）。

        仅已过审（review_status='approved'）的题目可发布；发布只改可见范围，
        不动 review_status —— 可见充要条件 ``shared ∧ approved`` 因此成立。
        """
        question = self._get(question_id)
        if question.review_status != REVIEW_STATUS_APPROVED:
            raise IllegalTransition("只有已通过审核的题目才能发布")
        question.visibility = VISIBILITY_SHARED
        self.db.flush()
        return question

    def archive(self, question_id: int) -> Question:
        """approved|shared → archived（终态，不再进入共享池）。"""
        question = self._get(question_id)
        self._apply_transition(question, "archive")
        self.db.flush()
        return question

    # ---- 编辑 ----

    def update(self, question_id: int, data: dict) -> Question:
        """编辑题面字段（仅 stem/options/answer/analysis/difficulty）。

        - 仅 ``draft``/``rejected`` 可编辑；
        - ``visibility`` 不在可编辑字段内（非法键被忽略式拒绝 → 400）；
        - ``options`` 写入 ``options_json``。
        """
        question = self._get(question_id)
        if question.review_status not in EDITABLE_REVIEW_STATUSES:
            raise QuestionNotEditable("仅草稿或被退回的题目可以编辑")
        unexpected = set(data) - EDITABLE_FIELDS
        if unexpected:
            raise QuestionReviewError(
                f"不允许编辑字段：{', '.join(sorted(unexpected))}"
            )
        for field, value in data.items():
            if field == "options":
                question.options_json = (
                    json.dumps(value, ensure_ascii=False) if value is not None else None
                )
            else:
                setattr(question, field, value)
        self.db.flush()
        return question
