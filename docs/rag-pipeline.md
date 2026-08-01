# RAG Pipeline

Retrieval-Augmented Generation lets the AI answer questions grounded in your uploaded documents.

---

## Overview

```
Upload file
    │
    ▼
app/rag/loader.py       — load file → list[Document]
    │
    ▼
app/rag/chunker.py      — split into overlapping chunks
    │
    ▼
app/rag/embedder.py     — embed chunks with FastEmbed (local, no API key)
    │
    ▼
Qdrant                  — store vectors with user_id + doc_id metadata
    │
    ▼
(on query)
    │
app/rag/embedder.py     — embed query
    │
    ▼
Qdrant search           — cosine similarity, user_id filter, score ≥ 0.70, top-5
    │
    ▼
Agent context           — results injected into LLM prompt
```

---

## Document Loading (`app/rag/loader.py`)

Supported formats and their loaders:

| Extension | Loader | Notes |
|---|---|---|
| `.pdf` | `PyPDFLoader` | Extracts text per page |
| `.docx` | `Docx2txtLoader` | Extracts plain text |
| `.txt` | `TextLoader` | UTF-8 encoding |

All loaders return `list[langchain_core.documents.Document]`.

Unsupported file types raise `DocumentProcessingError(422)`.

---

## Chunking (`app/rag/chunker.py`)

Uses `RecursiveCharacterTextSplitter`:

| Parameter | Value |
|---|---|
| `chunk_size` | 1000 characters |
| `chunk_overlap` | 200 characters |

Each chunk gets metadata injected:
```python
{
    "doc_id": "<document UUID>",
    "user_id": "<user UUID>",
    # plus any metadata from the loader (e.g. page number for PDFs)
}
```

---

## Embeddings (`app/rag/embedder.py`)

Uses **FastEmbed** — runs locally, no API key, no cost.

| Setting | Value |
|---|---|
| Model | `BAAI/bge-small-en-v1.5` (configurable via `EMBEDDING_MODEL`) |
| Dimensions | 384 (configurable via `EMBEDDING_DIMENSIONS`) |
| Execution | `asyncio.run_in_executor` (CPU-bound, thread pool) |

The model is lazy-loaded on first use and cached with `@lru_cache`. Subsequent embeddings reuse the same loaded model.

```python
class FastEmbedEmbedder:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]
    async def embed_query(self, text: str) -> list[float]
```

---

## Vector Storage (Qdrant)

Collection: `aurynix_docs` (configurable via `QDRANT_COLLECTION`)

Each point stored:
```json
{
    "id": "<uuid>",
    "vector": [0.123, -0.456, ...],
    "payload": {
        "page_content": "The termination clause states...",
        "doc_id": "<document UUID>",
        "user_id": "<user UUID>",
        "filename": "contract.pdf",
        "page": 3
    }
}
```

Collection settings:
- Distance metric: **Cosine**
- `on_disk: true` — vectors stored on disk, not in RAM

---

## Retrieval (`app/rag/retriever.py`)

Every search is **user-scoped** — users can only retrieve their own documents.

| Parameter | Value |
|---|---|
| `limit` | 5 results |
| `score_threshold` | 0.70 (cosine similarity) |
| Filter | `user_id == current_user.id` |

Optional `filename` filter allows searching within a specific document.

---

## RAG Tool (`app/tools/rag_tool.py`)

The agent accesses the RAG pipeline through a LangChain `@tool`:

```python
def make_rag_tool(user_id: str) -> BaseTool:
    @tool
    async def knowledge_base_search(query: str) -> str:
        """Search the user's uploaded document knowledge base."""
        ...
    return knowledge_base_search
```

**Why a factory?** The tool must close over the current `user_id` at request time. If the tool were created at startup with a placeholder, all users would search each other's documents.

The factory is called in `execute_tools_node` which reads `user_id` from the LangGraph state, ensuring isolation between users.

---

## Background Ingestion

When a document is uploaded via `POST /documents/upload`:

1. File is saved to `UPLOAD_DIR`
2. `Document` row is created with `status="processing"`
3. Response is returned **immediately** (`202 Accepted`)
4. `asyncio.create_task(_ingest_background(...))` fires the pipeline
5. On completion: `status="ready"`, `chunk_count=N`
6. On failure: `status="failed"`, `error_message="..."`

The background task creates its own database engine (cannot share the request session which is already closed by the time ingestion completes).

---

## Deleting Documents

`DELETE /documents/{id}` does two things:

1. Deletes the `Document` row from PostgreSQL
2. Deletes all Qdrant points with matching `doc_id` AND `user_id` (double-keyed for safety)

---

## Batch Ingestion Script

To ingest an entire directory of files for a specific user:

```bash
uv run python scripts/ingest_docs.py \
  --user-id <user-uuid> \
  --dir /path/to/documents/
```
