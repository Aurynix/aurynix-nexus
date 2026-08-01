from langchain_core.documents import Document
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.core.config import settings
from app.core.logging import get_logger
from app.database.qdrant import get_qdrant_client

logger = get_logger(__name__)


class QdrantRetriever:
    def __init__(
        self,
        limit: int = 5,
        score_threshold: float = 0.70,
    ) -> None:
        self._limit = limit
        self._score_threshold = score_threshold

    async def search(
        self,
        query_embedding: list[float],
        user_id: str,
        filename: str | None = None,
    ) -> list[Document]:
        client = await get_qdrant_client()

        must = [FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        if filename:
            must.append(FieldCondition(key="filename", match=MatchValue(value=filename)))

        results = await client.search(
            collection_name=settings.qdrant_collection,
            query_vector=query_embedding,
            limit=self._limit,
            score_threshold=self._score_threshold,
            query_filter=Filter(must=must),
            with_payload=True,
        )

        docs = []
        for hit in results:
            payload = hit.payload or {}
            docs.append(
                Document(
                    page_content=payload.get("page_content", ""),
                    metadata={
                        "doc_id": payload.get("doc_id"),
                        "user_id": payload.get("user_id"),
                        "filename": payload.get("filename"),
                        "page": payload.get("page"),
                        "score": hit.score,
                    },
                )
            )

        logger.debug("Qdrant search", user_id=user_id, hits=len(docs))
        return docs
