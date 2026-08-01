import uuid
from pathlib import Path

from langchain_core.documents import Document
from qdrant_client.http.models import PointStruct

from app.core.config import settings
from app.core.logging import get_logger
from app.database.qdrant import get_qdrant_client
from app.rag.chunker import DocumentChunker
from app.rag.embedder import OpenAIEmbedder
from app.rag.loader import load
from app.rag.retriever import QdrantRetriever

logger = get_logger(__name__)


class RAGPipeline:
    def __init__(self) -> None:
        self._embedder = OpenAIEmbedder()
        self._chunker = DocumentChunker()
        self._retriever = QdrantRetriever()

    async def ingest(self, file_path: Path, doc_id: str, user_id: str) -> int:
        docs = load(file_path)
        chunks = self._chunker.chunk(docs, doc_id=doc_id, user_id=user_id)

        texts = [c.page_content for c in chunks]
        embeddings = await self._embedder.embed_documents(texts)

        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "page_content": chunk.page_content,
                    "doc_id": doc_id,
                    "user_id": user_id,
                    "filename": file_path.name,
                    **{
                        k: v
                        for k, v in chunk.metadata.items()
                        if k not in ("doc_id", "user_id")
                    },
                },
            )
            for chunk, emb in zip(chunks, embeddings)
        ]

        client = await get_qdrant_client()
        await client.upsert(
            collection_name=settings.qdrant_collection,
            points=points,
        )

        logger.info("Document ingested", doc_id=doc_id, chunks=len(chunks))
        return len(chunks)

    async def query(self, text: str, user_id: str) -> list[Document]:
        embedding = await self._embedder.embed_query(text)
        return await self._retriever.search(embedding, user_id=user_id)

    async def delete_document(self, doc_id: str, user_id: str) -> None:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        client = await get_qdrant_client()
        await client.delete(
            collection_name=settings.qdrant_collection,
            points_selector=Filter(
                must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                ]
            ),
        )
        logger.info("Document vectors deleted", doc_id=doc_id)
