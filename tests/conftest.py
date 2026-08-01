import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.dependencies import get_async_session, get_current_user
from app.main import create_app
from app.models.base import Base
from app.models.user import User

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    from app.core.security import hash_password

    user = User(
        id=uuid.uuid4(),
        email="test@aurynix.test",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict[str, str]:
    from app.core.security import create_access_token

    token, _ = create_access_token(str(test_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client — get_current_user is overridden to return test_user."""
    app = create_app()

    app.dependency_overrides[get_async_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: test_user

    mock_graph = MagicMock()

    async def fake_stream_events(*args, **kwargs):
        yield {"event": "on_chat_model_stream", "name": "test", "data": {}}

    mock_graph.astream_events = fake_stream_events
    app.state.graph = mock_graph

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def unauth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated client — auth is NOT bypassed, 403s are expected."""
    app = create_app()

    app.dependency_overrides[get_async_session] = lambda: db_session

    mock_graph = MagicMock()
    app.state.graph = mock_graph

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def mock_openai_embeddings():
    with patch("app.rag.embedder.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )
        mock_cls.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_qdrant():
    with patch("app.database.qdrant.get_qdrant_client") as mock_fn:
        client = AsyncMock()
        client.search.return_value = []
        client.upsert.return_value = None
        mock_fn.return_value = client
        yield client
