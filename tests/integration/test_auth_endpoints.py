import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_returns_tokens(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@test.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient):
    payload = {"email": "dup@test.com", "password": "password123"}
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_valid_credentials(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "logintest@test.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "logintest@test.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wrongpw@test.com", "password": "correct123"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@test.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_profile(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "id" in data


@pytest.mark.asyncio
async def test_me_without_token_returns_403(unauth_client: AsyncClient):
    response = await unauth_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_liveness(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
