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
    created_at: datetime


class ParseResultOut(BaseModel):
    document_id: int
    chunks: int
    message: str


class GenerateFileQuestionsRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    question_type: str = Field(default="choice", pattern="^(choice|fill|short_answer)$")
