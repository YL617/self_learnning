from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


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
    created_at: datetime


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
