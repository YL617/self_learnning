from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DocumentOut(ORMModel):
    id: int
    filename: str
    file_type: str
    storage_path: str
    status: str
    chunks_count: int
    size_bytes: int = 0
    temp_cleanup_at: datetime | None = None
    created_at: datetime


class ParseResultOut(BaseModel):
    document_id: int
    chunks: int
    message: str


class QuestionTypeCount(BaseModel):
    question_type: str = Field(pattern="^(choice|fill|short_answer)$")
    count: int = Field(default=1, ge=1, le=20)


class GenerateFileQuestionsRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    question_type: str = Field(default="choice", pattern="^(choice|fill|short_answer)$")
    question_plan: list[QuestionTypeCount] | None = None


class FileAnalyzeOut(BaseModel):
    document_id: int
    knowledge_points: int
    completeness: str
    message: str
    menu: list[QuestionTypeCount]
