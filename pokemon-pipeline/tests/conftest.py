"""Shared pytest fixtures: in-memory SQLite DB session + fixture file loading helper."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.db import Base

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_vgc_team() -> str:
    return load_fixture("sample_vgc_team.txt")


@pytest.fixture
def sample_partial_team() -> str:
    return load_fixture("sample_partial_team.txt")


@pytest.fixture
def sample_smogon_team() -> str:
    return load_fixture("sample_smogon_team.txt")
