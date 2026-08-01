"""
Batch-ingest documents from a local directory into the knowledge base.

Usage:
    uv run python scripts/ingest_docs.py --user-id <UUID> --dir ./path/to/docs/

Supported file types: .pdf, .docx, .txt
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_SUPPORTED = {".pdf", ".docx", ".txt"}


async def ingest(user_id: str, directory: Path) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import settings
    from app.models.document import Document
    from app.rag.pipeline import RAGPipeline

    engine = create_async_engine(settings.async_database_url)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    pipeline = RAGPipeline()

    files = [f for f in directory.rglob("*") if f.suffix.lower() in _SUPPORTED]
    if not files:
        print(f"No supported files found in {directory}")
        return

    print(f"Found {len(files)} file(s) to ingest for user {user_id}\n")

    async with SessionLocal() as db:
        for file_path in files:
            doc_id = str(uuid.uuid4())
            print(f"  [{file_path.name}] ingesting ...")

            doc = Document(
                id=uuid.UUID(doc_id),
                user_id=uuid.UUID(user_id),
                filename=file_path.name,
                file_type=file_path.suffix.lstrip(".").lower(),
                file_size=file_path.stat().st_size,
                status="processing",
            )
            db.add(doc)
            await db.flush()

            try:
                chunk_count = await pipeline.ingest(file_path, doc_id=doc_id, user_id=user_id)
                doc.status = "ready"
                doc.chunk_count = chunk_count
                print(f"  [{file_path.name}] done — {chunk_count} chunks")
            except Exception as exc:
                doc.status = "failed"
                doc.error_message = str(exc)
                print(f"  [{file_path.name}] FAILED: {exc}")

            await db.commit()

    await engine.dispose()
    print("\nIngestion complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ingest documents into Aurynix Nexus")
    parser.add_argument("--user-id", required=True, help="UUID of the target user")
    parser.add_argument("--dir", required=True, type=Path, help="Directory containing documents")
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(f"Error: {args.dir} is not a directory")
        sys.exit(1)

    try:
        uuid.UUID(args.user_id)
    except ValueError:
        print(f"Error: '{args.user_id}' is not a valid UUID")
        sys.exit(1)

    asyncio.run(ingest(args.user_id, args.dir))


if __name__ == "__main__":
    main()
