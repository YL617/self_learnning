from pydantic import BaseModel, Field

from app.schemas.plan import StudyPlanOut
from app.schemas.user import UserProfileOut


class OnboardingIn(BaseModel):
    major: str | None = Field(default=None, max_length=100)
    grade: str | None = Field(default=None, max_length=50)
    goals: list[str] = Field(default_factory=list)
    weekly_minutes: int | None = Field(default=None, ge=60, le=10080)
    learning_style: list[str] = Field(default_factory=list)
    pain_point: list[str] = Field(default_factory=list)
    school_level: str | None = Field(default=None, max_length=64)
    available_time_slots: list[str] = Field(default_factory=list)
    generate_plan: bool = True
    complete: bool = True


class OnboardingOut(BaseModel):
    profile: UserProfileOut
    plan: StudyPlanOut | None = None
