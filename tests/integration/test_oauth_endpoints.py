import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_oauth_status_requires_auth(unauth_client: AsyncClient):
    response = await unauth_client.get("/api/v1/oauth/google/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_oauth_status_returns_not_connected(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/oauth/google/status", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["scopes"] == []


@pytest.mark.asyncio
async def test_oauth_disconnect_requires_auth(unauth_client: AsyncClient):
    response = await unauth_client.delete("/api/v1/oauth/google/disconnect")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_oauth_disconnect_no_token_returns_204(client: AsyncClient, auth_headers: dict):
    response = await client.delete("/api/v1/oauth/google/disconnect", headers=auth_headers)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_oauth_authorize_requires_auth(unauth_client: AsyncClient):
    response = await unauth_client.get("/api/v1/oauth/google/authorize")
    assert response.status_code == 401
