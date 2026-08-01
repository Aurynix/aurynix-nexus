import pytest
from langchain_core.documents import Document

from app.rag.chunker import DocumentChunker


def test_chunker_injects_metadata():
    chunker = DocumentChunker(chunk_size=500, chunk_overlap=50)
    docs = [Document(page_content="word " * 200, metadata={"page": 1})]
    chunks = chunker.chunk(docs, doc_id="doc-001", user_id="user-001")

    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.metadata["doc_id"] == "doc-001"
        assert chunk.metadata["user_id"] == "user-001"


def test_chunker_produces_multiple_chunks():
    chunker = DocumentChunker(chunk_size=200, chunk_overlap=20)
    docs = [Document(page_content="token " * 300, metadata={})]
    chunks = chunker.chunk(docs, doc_id="d", user_id="u")
    assert len(chunks) >= 2


def test_chunker_short_doc_single_chunk():
    chunker = DocumentChunker(chunk_size=1000, chunk_overlap=100)
    docs = [Document(page_content="short text", metadata={})]
    chunks = chunker.chunk(docs, doc_id="d", user_id="u")
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_embedder_batches(mock_openai_embeddings):
    from app.rag.embedder import OpenAIEmbedder

    embedder = OpenAIEmbedder()
    texts = [f"sentence {i}" for i in range(150)]
    embeddings = await embedder.embed_documents(texts)
    assert len(embeddings) == 150
    assert mock_openai_embeddings.embeddings.create.call_count == 2


@pytest.mark.asyncio
async def test_embedder_single_query(mock_openai_embeddings):
    from app.rag.embedder import OpenAIEmbedder

    embedder = OpenAIEmbedder()
    embedding = await embedder.embed_query("what is the revenue?")
    assert len(embedding) == 1536
