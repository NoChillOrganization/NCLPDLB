"""Asyncpg pool + plain-SQL migration runner."""

import hashlib
from pathlib import Path

import asyncpg

from src.platform.config import PLATFORM_DATABASE_URL

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(PLATFORM_DATABASE_URL)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def migrate() -> list[str]:
    """Apply pending migrations from migrations/*.sql in filename order. Idempotent."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migration "
            "(filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {
            r["filename"]
            for r in await conn.fetch("SELECT filename FROM schema_migration")
        }
        ran = []
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migration (filename) VALUES ($1)", path.name
                )
            ran.append(path.name)
        return ran


def payload_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()
