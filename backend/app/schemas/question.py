from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class QuestionGenerateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    knowledge_point: str = Field(min_length=1, max_length=200)
    count: int = Field(default=5, ge=1, le=20)
    question_type: str = Field(default="choice", pattern="^(choice|fill|short_answer)$")
    document_id: int | None = None
    reference_question_id: int | None = None
    # Phase 2：可选的结构化知识点；不传时行为与旧版完全一致。
    knowledge_point_id: int | None = None


class QuestionOut(ORMModel):
    id: int
    subject: str
    knowledge_point: str
    question_type: str
    stem: str
    options_json: str | None = None
    answer: str
    analysis: str | None = None
    source: str
    is_favorite: bool = False


class QuestionFavoriteUpdate(BaseModel):
    is_favorite: bool


class AnswerSubmit(BaseModel):
    user_answer: str = Field(min_length=1, max_length=2000)
    # 大阶段 2：可选作答耗时，仅作为评估上下文，不参与正确答案判定。
    spent_seconds: int = Field(default=0, ge=0, le=86400)


class AnswerOut(ORMModel):
    id: int
    question_id: int
    user_answer: str
    is_correct: bool
    created_at: datetime


class WrongBookOut(ORMModel):
    id: int
    question_id: int
    review_count: int
    mastered: bool
    review_stage: int = 1
    next_review_date: date | None = None
    last_reviewed_at: datetime | None = None
    created_at: datetime
    question: QuestionOut | None = None


class WrongBookItemUpdate(BaseModel):
    # mastered 显式非空表示"标记/取消掌握"；reviewed 表示"完成一次复习"。
    mastered: bool | None = None
    reviewed: bool = False


class QuestionKnowledgePointAttachItem(BaseModel):
    knowledge_point_id: int
    role: Literal["primary", "secondary"] = "primary"


class QuestionKnowledgePointReplaceRequest(BaseModel):
    items: list[QuestionKnowledgePointAttachItem] = Field(max_length=20)


class QuestionKnowledgePointRead(ORMModel):
    id: int
    question_id: int
    knowledge_point_id: int
    role: str
    source: str
    created_at: datetime
