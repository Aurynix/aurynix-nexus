"""
Initialize Aurynix Nexus database:
  1. Run Alembic migrations (creates all tables)
  2. Ensure Qdrant collection exists
  3. Set up LangGraph checkpoint + memory store tables

Usage:
    uv run python scripts/init_db.py
"""
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def run_migrations() -> None:
    print("Running Alembic migrations...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        text=True,
    )
    print("Migrations complete.")


async def init_qdrant() -> None:
    print("Initializing Qdrant collection...")
    from app.database.qdrant import ensure_collection
    await ensure_collection()
    print("Qdrant collection ready.")


async def init_langgraph() -> None:
    print("Initializing LangGraph checkpointer tables...")
    from app.memory.checkpointer import get_checkpointer
    await get_checkpointer()
    print("Initializing LangGraph memory store tables...")
    from app.memory.store import get_memory_store
    await get_memory_store()
    print("LangGraph tables ready.")


async def main() -> None:
    run_migrations()
    await init_qdrant()
    await init_langgraph()
    print("\nDatabase initialization complete. Ready to launch.")


if __name__ == "__main__":
    asyncio.run(main())
