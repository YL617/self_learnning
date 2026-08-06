from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PlanChatMessageOut(ORMModel):
    id: int
    role: str
    content: str
    created_at: datetime


class PlanChatStartOut(BaseModel):
    session_id: int
    reply: str
    status: str


class PlanChatSendIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class PlanChatReply(BaseModel):
    session_id: int
    reply: str
    status: str
    draft: dict[str, Any] | None = None


class PlanChatConfirmOut(BaseModel):
    plan_id: int
    message: str
