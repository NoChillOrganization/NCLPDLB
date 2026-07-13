"""Shared FastAPI dependencies: DB session and X-API-Key admin auth."""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.db import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_secret_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")
