from datetime import date, datetime, timezone

from pydantic import BaseModel, Field, field_serializer

from app.schemas.common import ORMModel


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date


class TodoUpdate(BaseModel):
    completed: bool | None = None


class TodoOut(ORMModel):
    id: int
    title: str
    due_date: date
    completed: bool


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    remind_at: datetime


class ReminderOut(ORMModel):
    id: int
    title: str
    remind_at: datetime
    triggered: bool
    dismissed: bool

    @field_serializer("remind_at")
    def _serialize_remind_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    remind_at: datetime | None = None

    @field_serializer("remind_at")
    def _serialize_remind_at(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()


class CalendarEventOut(BaseModel):
    date: date
    title: str
    kind: str
    id: int
    completed: bool


class CourseChapterOut(ORMModel):
    id: int
    title: str
    order_index: int


class CourseOut(ORMModel):
    id: int
    title: str
    platform: str
    url: str
    description: str | None = None
    chapters: list[CourseChapterOut] = Field(default_factory=list)


class WeeklyReportOut(BaseModel):
    start_date: date
    end_date: date
    focus_minutes: int
    sessions: int
    answered: int
    correct: int
    coins_earned: int
    wrong_added: int


class DemoSeedOut(BaseModel):
    message: str
    todos: int
    reminders: int
    sessions: int
    courses: int
