from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.dependencies import CurrentUser, DbSession, RedisClient
from app.core.exceptions import AuthenticationError
from app.core.security import decode_token
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=True)


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, db: DbSession) -> TokenResponse:
    return await auth_service.register(body.email, body.password, db)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DbSession) -> TokenResponse:
    return await auth_service.login(body.email, body.password, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, redis: RedisClient) -> TokenResponse:
    return await auth_service.refresh_tokens(body.refresh_token, redis)


@router.post("/logout", status_code=204)
async def logout(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    current_user: CurrentUser,
    redis: RedisClient,
) -> None:
    payload = decode_token(credentials.credentials)
    if payload:
        await auth_service.logout(payload, redis)


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
