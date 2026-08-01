import asyncio
from functools import lru_cache

from fastembed import TextEmbedding

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_model(model_name: str) -> TextEmbedding:
    return TextEmbedding(model_name=model_name)


class FastEmbedEmbedder:
    def __init__(self) -> None:
        self._model_name = settings.embedding_model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_event_loop()
        model = _get_model(self._model_name)
        embeddings = await loop.run_in_executor(None, lambda: list(model.embed(texts)))
        logger.debug("Embedded documents", count=len(texts), model=self._model_name)
        return [e.tolist() for e in embeddings]

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_documents([text])
        return results[0]
