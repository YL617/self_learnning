from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class KnowledgePointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    description: str | None = None
    status: Literal["active", "pending", "disabled"] = "active"
    source: Literal["system", "admin", "ai"] = "admin"


class KnowledgePointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    subject: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = None
    description: str | None = None
    status: Literal["active", "pending", "disabled"] | None = None


class KnowledgePointRead(ORMModel):
    id: int
    name: str
    normalized_name: str
    subject: str
    parent_id: int | None = None
    description: str | None = None
    status: str
    source: str
    created_at: datetime
    updated_at: datetime


class KnowledgePointTreeNode(KnowledgePointRead):
    children: list["KnowledgePointTreeNode"] = Field(default_factory=list)
