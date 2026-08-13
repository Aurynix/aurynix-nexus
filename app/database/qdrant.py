from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_qdrant_client: AsyncQdrantClient | None = None


async def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        if settings.qdrant_use_https or settings.qdrant_api_key:
            _qdrant_client = AsyncQdrantClient(
                url=f"https://{settings.qdrant_host}",
                api_key=settings.qdrant_api_key or None,
            )
        else:
            _qdrant_client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )
    return _qdrant_client


async def close_qdrant() -> None:
    global _qdrant_client
    if _qdrant_client is not None:
        await _qdrant_client.close()
        _qdrant_client = None


async def ensure_collection() -> None:
    client = await get_qdrant_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]

    if settings.qdrant_collection not in names:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
                on_disk=True,
            ),
        )
        logger.info("Qdrant collection created", collection=settings.qdrant_collection)
    else:
        logger.info("Qdrant collection exists", collection=settings.qdrant_collection)


async def check_qdrant_health() -> bool:
    try:
        client = await get_qdrant_client()
        await client.get_collections()
        return True
    except Exception:
        return False
