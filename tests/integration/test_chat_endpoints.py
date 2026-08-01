import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_chat_stream_requires_auth(unauth_client: AsyncClient):
    response = await unauth_client.post(
        "/api/v1/chat/stream",
        json={"message": "hello"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chat_stream_returns_sse(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/chat/stream",
        json={"message": "What is in my documents?"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/chat/conversations", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_nonexistent_conversation_returns_404(client: AsyncClient, auth_headers: dict):
    import uuid

    response = await client.get(
        f"/api/v1/chat/conversations/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_memory_list_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/memory", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_memory_create_and_delete(client: AsyncClient, auth_headers: dict):
    create_response = await client.post(
        "/api/v1/memory",
        json={"key": "role", "value": "product manager", "source": "manual"},
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    fact_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/memory/{fact_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204
