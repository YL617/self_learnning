from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class FocusSessionStart(BaseModel):
    task_label: str = Field(default="专注学习", max_length=200)
    duration_minutes: int = Field(default=25, ge=1, le=180)
    tag_color: str | None = Field(default=None, max_length=16)


class FocusSessionOut(ORMModel):
    id: int
    task_label: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: int
    completed: bool
    tag_color: str | None = None


class FocusTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str = Field(default="#0f766e", max_length=16)


class FocusTagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = Field(default=None, max_length=16)


class FocusTagOut(ORMModel):
    id: int
    name: str
    color: str
    created_at: datetime


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
    play_count_today: int = 0
    playing_until: datetime | None = None
    last_fed_at: datetime | None = None


class PetPlaySessionOut(ORMModel):
    id: int
    status: str = "active"
    started_at: datetime
    ended_at: datetime | None = None
    duration_minutes: int
    coin_cost: int
    mood_gain: int
    exp_gain: int
    hunger_loss: int
    created_at: datetime


class PetPlaySummaryOut(BaseModel):
    elapsed_minutes: int
    mood_gain: int
    exp_gain: int
    hunger_loss: int
    coins_spent: int
    message: str


class PetPlayStateOut(BaseModel):
    session: PetPlaySessionOut | None = None
    summary: PetPlaySummaryOut | None = None
    pet: PetOut


class PetMessageOut(ORMModel):
    id: int
    role: str
    kind: str = "chat"
    content: str
    created_at: datetime


class PetUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class FeedPetRequest(BaseModel):
    amount: int = Field(default=10, ge=1, le=100)


class PetChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class PetChatOut(BaseModel):
    reply: str
    pet: PetOut
    messages: list[PetMessageOut]


class PetInteractionOut(BaseModel):
    reply: str
    pet: PetOut


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
