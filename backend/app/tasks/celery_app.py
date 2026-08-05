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
