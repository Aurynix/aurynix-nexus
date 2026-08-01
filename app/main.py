from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.middleware import RequestIDMiddleware
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.exceptions import AurynixError
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Starting Aurynix Nexus", environment=settings.environment)

    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    from app.agents.graphs import build_graph
    from app.database.qdrant import ensure_collection
    from app.memory.checkpointer import get_checkpointer
    from app.memory.store import get_memory_store

    await ensure_collection()

    checkpointer = await get_checkpointer()
    memory_store = await get_memory_store()
    graph = build_graph(checkpointer=checkpointer, store=memory_store)

    app.state.checkpointer = checkpointer
    app.state.memory_store = memory_store
    app.state.graph = graph

    logger.info("Aurynix Nexus started successfully")
    yield

    from app.database.postgres import engine
    from app.database.qdrant import close_qdrant
    from app.database.redis import close_redis
    from app.memory.checkpointer import close_checkpointer
    from app.memory.store import close_memory_store

    await close_redis()
    await close_qdrant()
    await close_checkpointer()
    await close_memory_store()
    await engine.dispose()

    logger.info("Aurynix Nexus shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Aurynix Nexus",
        description="AI-powered business assistant with RAG, memory, and multi-agent workflows",
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    @app.exception_handler(AurynixError)
    async def aurynix_exception_handler(request: Request, exc: AurynixError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    app.include_router(v1_router)

    return app


app = create_app()
