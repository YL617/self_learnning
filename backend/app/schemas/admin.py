from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.question import QuestionKnowledgePointRead


class AdminUserOut(ORMModel):
    id: int
    email: str
    username: str
    nickname: str | None = None
    membership_level: str = "free"
    membership_expires_at: datetime | None = None
    role: str = "user"
    is_active: bool = True
    created_at: datetime


class AdminUserUpdate(BaseModel):
    membership_level: str | None = Field(
        default=None, pattern="^(free|basic|advanced|full)$"
    )
    membership_expires_at: datetime | None = None
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    is_active: bool | None = None


class AiMonitorSnapshotOut(ORMModel):
    id: int
    provider: str
    total_balance: str = "0"
    granted_balance: str = "0"
    topped_up_balance: str = "0"
    is_available: bool = True
    status: str = "ok"
    error_message: str | None = None
    checked_at: datetime


class AiUsageOut(ORMModel):
    id: int
    provider: str
    usage_date: date
    tokens: int = 0
    cost: float = 0
    recorded_at: datetime


class AiMonitorOut(BaseModel):
    provider: str = "deepseek"
    snapshot: AiMonitorSnapshotOut | None = None
    usage: list[AiUsageOut] = Field(default_factory=list)
    is_low_balance: bool = False
    low_balance_threshold: float = 10.0


class StatsOverviewOut(BaseModel):
    user_count: int
    active_today: int
    plan_count: int
    question_count: int
    wrong_book_count: int
    document_count: int
    course_count: int
    total_focus_minutes: int
    total_coins_issued: int
    ai_monitor: AiMonitorOut | None = None


class AdminQuestionOut(ORMModel):
    id: int
    user_id: int
    subject: str
    knowledge_point: str
    question_type: str
    stem: str
    source: str
    is_favorite: bool = False
    difficulty: str | None = None
    visibility: str = "private"
    review_status: str = "draft"
    created_at: datetime


class AdminQuestionCreate(BaseModel):
    """M4：管理员创建题目（共享题库 / 私题均可）。"""

    subject: str = Field(min_length=1, max_length=100)
    knowledge_point: str = Field(min_length=1, max_length=200)
    question_type: str = Field(default="choice", pattern="^(choice|fill|short_answer)$")
    stem: str = Field(min_length=1, max_length=4000)
    options: list[str] = Field(default_factory=list, max_length=10)
    answer: str = Field(min_length=1, max_length=2000)
    analysis: str | None = Field(default=None, max_length=4000)
    difficulty: str | None = Field(default=None, pattern="^(easy|medium|hard)$")
    visibility: str = Field(default="shared", pattern="^(private|shared)$")
    # 可选：创建时一并绑定知识点（仅 concept；第一个作为 primary）。
    knowledge_point_ids: list[int] = Field(default_factory=list, max_length=20)


class AdminQuestionKnowledgePointAttach(BaseModel):
    knowledge_point_id: int
    role: str = Field(default="primary", pattern="^(primary|secondary)$")


class AdminQuestionDetailOut(ORMModel):
    """M4：题目详情（全字段 + 结构化知识点关联）。"""

    id: int
    user_id: int
    subject: str
    knowledge_point: str
    question_type: str
    stem: str
    options_json: str | None = None
    answer: str
    analysis: str | None = None
    source: str
    is_favorite: bool = False
    difficulty: str | None = None
    visibility: str = "private"
    # M5.5 P4-1/P4-2：审核生命周期与留痕。
    review_status: str = "draft"
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime
    knowledge_points: list[QuestionKnowledgePointRead] = Field(default_factory=list)


class QuestionUpdate(BaseModel):
    """M5.5 P4-2：管理员编辑题目（仅 draft/rejected 状态可编辑）。

    可编辑字段严格限定为题面内容：stem/options/answer/analysis/difficulty。

    - **``visibility`` 不在可编辑字段内**：发布只能经 ``publish`` 状态转移端点，
      禁止绕过审核直接改可见范围。
    - ``subject``/``question_type`` 也不可改（避免与已绑定知识点的学科失配）。
    """

    stem: str | None = Field(default=None, min_length=1, max_length=4000)
    options: list[str] | None = Field(default=None, max_length=10)
    answer: str | None = Field(default=None, min_length=1, max_length=2000)
    analysis: str | None = Field(default=None, max_length=4000)
    difficulty: str | None = Field(default=None, pattern="^(easy|medium|hard)$")


class QuestionReviewAction(BaseModel):
    """M5.5 P4-2：审核动作入参（目前仅 reject 使用 note）。"""

    note: str | None = Field(default=None, max_length=2000)


class QuestionReviewOut(ORMModel):
    """M5.5 P4-2：审核状态与留痕快照（状态转移端点统一返回）。"""

    id: int
    review_status: str
    visibility: str
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None


class KnowledgeCoverageItem(BaseModel):
    subject: str
    concept_total: int
    covered: int
    uncovered: int
    question_total: int


class KnowledgeCoverageOut(BaseModel):
    """M4：知识覆盖情况（只统计 concept；container 永不计入）。"""

    concept_total: int
    covered: int
    uncovered: int
    question_total: int
    items: list[KnowledgeCoverageItem] = Field(default_factory=list)


class CourseChapterIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    order_index: int = 0


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    platform: str = Field(min_length=1, max_length=64)
    url: str = Field(min_length=1, max_length=500)
    description: str | None = None
    chapters: list[CourseChapterIn] = Field(default_factory=list)


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    platform: str | None = Field(default=None, min_length=1, max_length=64)
    url: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    chapters: list[CourseChapterIn] | None = None
