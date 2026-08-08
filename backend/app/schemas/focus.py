from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class FocusSessionStart(BaseModel):
    task_label: str = Field(default="专注学习", max_length=200)
    duration_minutes: int = Field(default=25, ge=1, le=180)


class FocusSessionOut(ORMModel):
    id: int
    task_label: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: int
    completed: bool


class FocusStatsOut(BaseModel):
    total_minutes: int
    session_count: int
    today_minutes: int


class PetOut(ORMModel):
    id: int
    name: str
    level: int
    exp: int
    mood: int
    hunger: int = 100
    evolution_stage: int = 1
    runaway: bool = False
    last_fed_at: datetime | None = None


class PetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class FeedPetRequest(BaseModel):
    amount: int = Field(default=10, ge=1, le=100)


class FocusCompleteRequest(BaseModel):
    verified: bool = True


class ShopItemOut(ORMModel):
    id: int
    name: str
    price: int
    effect_type: str
    description: str | None = None


class CoinTransactionOut(ORMModel):
    id: int
    amount: int
    reason: str
    created_at: datetime
