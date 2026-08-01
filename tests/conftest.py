import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

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
    conn = await test_engine.connect()
    await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        await conn.rollback()
        await conn.close()


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
def mock_fastembed():
    import numpy as np

    with patch("app.rag.embedder._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.embed.side_effect = lambda texts: [np.array([0.1] * 384) for _ in texts]
        mock_get_model.return_value = mock_model
        yield mock_model


@pytest.fixture
def mock_qdrant():
    with patch("app.database.qdrant.get_qdrant_client") as mock_fn:
        client = AsyncMock()
        client.search.return_value = []
        client.upsert.return_value = None
        mock_fn.return_value = client
        yield client
