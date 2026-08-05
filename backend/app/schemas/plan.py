from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PlanGenerateRequest(BaseModel):
    major: str = Field(min_length=1, max_length=100)
    grade: str = Field(default="大一", max_length=50)
    goal: str = Field(min_length=1, max_length=500)
    daily_minutes: int = Field(default=60, ge=10, le=600)
    weeks: int = Field(default=4, ge=1, le=12)
    subjects: list[str] = Field(default_factory=list)


class StudyPlanCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str | None = None
    start_date: date
    end_date: date


class PlanItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subject: str | None = None
    scheduled_date: date
    duration_minutes: int = Field(default=60, ge=1, le=600)


class PlanItemUpdate(BaseModel):
    completed: bool | None = None


class PlanItemOut(ORMModel):
    id: int
    plan_id: int
    title: str
    subject: str | None = None
    scheduled_date: date
    duration_minutes: int
    completed: bool
    order_index: int


class StudyPlanOut(ORMModel):
    id: int
    title: str
    goal: str | None = None
    start_date: date
    end_date: date
    status: str
    created_at: datetime
    items: list[PlanItemOut] = Field(default_factory=list)
