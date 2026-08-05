from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RAGEngine:
    """基于 Chroma 的轻量 RAG；Milvus / LlamaIndex 可按需替换。"""

    def __init__(self) -> None:
        self.collection_name = settings.CHROMA_COLLECTION
        self.persist_dir = str(settings.VECTOR_DB_DIR)
        self._collection: Any = None

    def _ensure_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            import chromadb

            client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = client.get_or_create_collection(self.collection_name)
        except ImportError:
            logger.warning("chromadb 未安装，向量检索降级为直接上下文返回")
            self._collection = None
        return self._collection

    def add_chunks(self, document_id: int, chunks: list[str]) -> None:
        collection = self._ensure_collection()
        if collection is None or not chunks:
            return
        ids = [f"doc-{document_id}-{idx}" for idx in range(len(chunks))]
        metadatas = [{"document_id": document_id} for _ in chunks]
        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)

    def search(self, query: str, top_k: int = 5) -> list[str]:
        collection = self._ensure_collection()
        if collection is None:
            return [query]
        result = collection.query(query_texts=[query], n_results=top_k)
        documents = result.get("documents") or [[]]
        return [str(item) for item in (documents[0] if documents else []) if item]
