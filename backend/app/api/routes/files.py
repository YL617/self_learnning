import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Document, FileAnalyzeResult, KnowledgeChunk, Question, User
from app.schemas.file import (
    DocumentOut,
    FileAnalyzeOut,
    GenerateFileQuestionsRequest,
    ParseResultOut,
    QuestionTypeCount,
)
from app.schemas.question import QuestionOut
from app.services.document_parser import chunk_text, extract_text
from app.services.file_analyzer import analyze_document
from app.services.question_generator import generate_questions
from app.services.rag import RAGEngine

router = APIRouter(prefix="/files", tags=["files"])
settings = get_settings()
ALLOWED_SUFFIXES = {".pdf", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
MAX_FILES_PER_USER = 5
MAX_TOTAL_BYTES = 50 * 1024 * 1024


def _get_own_document(db: Session, user_id: int, document_id: int) -> Document:
    document = db.scalar(
        select(Document).where(Document.id == document_id, Document.user_id == user_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    return document


@router.post("/upload", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 PDF / Word / PPT / TXT / 图片",
        )
    user_dir = settings.UPLOAD_DIR / f"user_{current_user.id}"
    user_dir.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    documents = list(
        db.scalars(
            select(Document).where(Document.user_id == current_user.id)
        ).all()
    )
    if len(documents) >= MAX_FILES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"最多同时保存 {MAX_FILES_PER_USER} 个文件，请先清理或升级会员",
        )
    total_size = sum(doc.size_bytes for doc in documents) + len(content)
    if total_size > MAX_TOTAL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件总大小超过 50MB 限制",
        )
    storage_path = user_dir / f"{uuid4().hex}{suffix}"
    storage_path.write_bytes(content)

    document = Document(
        user_id=current_user.id,
        filename=file.filename or storage_path.name,
        file_type=suffix.lstrip("."),
        storage_path=str(storage_path),
        status="uploaded",
        size_bytes=len(content),
        temp_cleanup_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.get("", response_model=list[DocumentOut])
def list_files(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == current_user.id)
            .order_by(Document.created_at.desc())
        ).all()
    )


@router.post("/{document_id}/parse", response_model=ParseResultOut)
def parse_document(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ParseResultOut:
    document = _get_own_document(db, current_user.id, document_id)
    try:
        text = extract_text(document.storage_path, document.file_type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    chunks = chunk_text(text) if text else []
    if not chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未能从文档中提取文本")
    document.status = "parsed"
    document.chunks_count = len(chunks)
    for index, content in enumerate(chunks):
        db.add(
            KnowledgeChunk(document_id=document.id, chunk_index=index, content=content)
        )
    db.commit()
    RAGEngine().add_chunks(document.id, chunks)
    return ParseResultOut(document_id=document.id, chunks=len(chunks), message="解析完成")


@router.post("/{document_id}/analyze", response_model=FileAnalyzeOut)
def analyze_file(
    document_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FileAnalyzeOut:
    document = _get_own_document(db, current_user.id, document_id)
    if document.status != "parsed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文档尚未解析")
    chunks = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
        .limit(12)
    ).all()
    result = analyze_document(
        document.filename,
        [chunk.content for chunk in chunks],
    )
    db.execute(
        sa_delete(FileAnalyzeResult).where(
            FileAnalyzeResult.document_id == document.id
        )
    )
    db.add(
        FileAnalyzeResult(
            document_id=document.id,
            menu_json=json.dumps(result, ensure_ascii=False),
            message=result["message"],
        )
    )
    db.commit()
    return FileAnalyzeOut(
        document_id=document.id,
        knowledge_points=result["knowledge_points"],
        completeness=result["completeness"],
        message=result["message"],
        menu=[QuestionTypeCount(**item) for item in result["menu"]],
    )


@router.post("/{document_id}/questions", response_model=list[QuestionOut], status_code=status.HTTP_201_CREATED)
def generate_file_questions(
    document_id: int,
    data: GenerateFileQuestionsRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Question]:
    document = _get_own_document(db, current_user.id, document_id)
    if document.status != "parsed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文档尚未解析")
    chunks = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
        .limit(8)
    ).all()
    context = [chunk.content for chunk in chunks]
    if data.question_plan:
        questions: list[dict] = []
        for item in data.question_plan:
            questions.extend(
                generate_questions(
                    subject="综合",
                    knowledge_point=f"《{document.filename}》",
                    count=item.count,
                    question_type=item.question_type,
                    context=context,
                )
            )
    else:
        questions = generate_questions(
            subject="综合",
            knowledge_point=f"《{document.filename}》",
            count=data.count,
            question_type=data.question_type,
            context=context,
        )
    saved: list[Question] = []
    for question in questions:
        model = Question(
            user_id=current_user.id,
            document_id=document.id,
            subject=question["subject"],
            knowledge_point=question["knowledge_point"],
            question_type=question["question_type"],
            stem=question["stem"],
            options_json=json.dumps(question.get("options", []), ensure_ascii=False),
            answer=question["answer"],
            analysis=question["analysis"],
        )
        db.add(model)
        saved.append(model)
    db.commit()
    for model in saved:
        db.refresh(model)
    return saved
