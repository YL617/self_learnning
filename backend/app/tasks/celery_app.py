from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ai_study",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_acks_late=True,
)


@celery_app.task(name="documents.parse_and_index")
def parse_and_index(document_id: int) -> dict:
    from app.core.database import SessionLocal
    from app.models import Document, KnowledgeChunk
    from app.services.document_parser import chunk_text, extract_text
    from app.services.rag import RAGEngine

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return {"ok": False, "reason": "document not found"}
        text = extract_text(document.storage_path, document.file_type)
        chunks = chunk_text(text) if text else []
        document.status = "parsed" if chunks else "failed"
        document.chunks_count = len(chunks)
        for index, content in enumerate(chunks):
            db.add(
                KnowledgeChunk(document_id=document.id, chunk_index=index, content=content)
            )
        db.commit()
        if chunks:
            RAGEngine().add_chunks(document.id, chunks)
        return {"ok": bool(chunks), "chunks": len(chunks)}


@celery_app.task(name="documents.cleanup_expired")
def cleanup_expired_documents() -> dict:
    from datetime import datetime, timezone
    from pathlib import Path

    from sqlalchemy import delete as sa_delete
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Document, FileAnalyzeResult, KnowledgeChunk

    with SessionLocal() as db:
        expired = list(
            db.scalars(
                select(Document).where(
                    Document.temp_cleanup_at <= datetime.now(timezone.utc)
                )
            ).all()
        )
        for document in expired:
            db.execute(
                sa_delete(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == document.id
                )
            )
            db.execute(
                sa_delete(FileAnalyzeResult).where(
                    FileAnalyzeResult.document_id == document.id
                )
            )
            path = Path(document.storage_path)
            if path.exists():
                path.unlink()
            db.delete(document)
        db.commit()
        return {"ok": True, "cleaned": len(expired)}


@celery_app.task(name="reminders.notify_due")
def notify_due_reminders() -> dict:
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Reminder

    with SessionLocal() as db:
        due = list(
            db.scalars(
                select(Reminder).where(
                    Reminder.remind_at <= datetime.now(timezone.utc),
                    Reminder.triggered.is_(False),
                )
            ).all()
        )
        for reminder in due:
            reminder.triggered = True
        db.commit()
        return {"ok": True, "triggered": len(due)}


@celery_app.task(name="ai_monitor.refresh_deepseek")
def refresh_ai_monitor_snapshot() -> dict:
    from app.core.database import SessionLocal
    from app.services.ai_monitor import refresh_deepseek_monitor

    with SessionLocal() as db:
        snapshot = refresh_deepseek_monitor(db)
        return {
            "ok": snapshot.status == "ok",
            "provider": snapshot.provider,
            "status": snapshot.status,
        }
