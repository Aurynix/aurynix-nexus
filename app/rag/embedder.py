from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_BATCH_SIZE = 100


class OpenAIEmbedder:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_embedding_model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            response = await self._client.embeddings.create(model=self._model, input=batch)
            all_embeddings.extend([item.embedding for item in response.data])
        logger.debug("Embedded documents", count=len(texts), model=self._model)
        return all_embeddings

    async def embed_query(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(model=self._model, input=[text])
        return response.data[0].embedding
