from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ActivateIn(BaseModel):
    code: str = Field(min_length=4, max_length=64)


class ActivationCodeOut(ORMModel):
    id: int
    code: str
    tier: str
    days: int
    status: str = "unused"
    used_by: int | None = None
    used_at: datetime | None = None
    created_at: datetime


class ActivationCodeCreate(BaseModel):
    tier: str = Field(pattern="^(basic|advanced|full)$")
    days: int = Field(ge=1, le=366)
    count: int = Field(default=1, ge=1, le=50)
