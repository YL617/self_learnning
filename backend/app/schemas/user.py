from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    account: str
    password: str


class UserProfileOut(ORMModel):
    major: str | None = None
    grade: str | None = None
    goals: str | None = None
    daily_study_minutes: int = 60
    weak_subjects: str | None = None
    school_level: str | None = None
    pain_point: str | None = None
    learning_style: str | None = None
    weekly_study_minutes: int = 420
    available_time_slots: str | None = None
    onboarding_completed: bool = False
    onboarding_completed_at: datetime | None = None


class UserOut(ORMModel):
    id: int
    email: str
    username: str
    membership_level: str = "free"
    profile: UserProfileOut | None = None


class UserProfileUpdate(BaseModel):
    major: str | None = None
    grade: str | None = None
    goals: str | None = None
    daily_study_minutes: int | None = Field(default=None, ge=10, le=600)
    weak_subjects: str | None = None
    school_level: str | None = None
    pain_point: str | None = None
    learning_style: str | None = None
    weekly_study_minutes: int | None = Field(default=None, ge=60, le=10080)
    available_time_slots: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
