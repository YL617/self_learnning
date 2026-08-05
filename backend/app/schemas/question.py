from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class QuestionGenerateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=100)
    knowledge_point: str = Field(min_length=1, max_length=200)
    count: int = Field(default=5, ge=1, le=20)
    question_type: str = Field(default="choice", pattern="^(choice|fill|short_answer)$")
    document_id: int | None = None


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


class AnswerSubmit(BaseModel):
    user_answer: str = Field(min_length=1, max_length=2000)


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
    created_at: datetime
    question: QuestionOut | None = None


class WrongBookItemUpdate(BaseModel):
    mastered: bool | None = None
