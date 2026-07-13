"""Populate sources table with the 5 known platforms. Idempotent (ON CONFLICT DO NOTHING)."""

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from config import settings
from models.db import Source, async_session_factory

SOURCES = [
    {
        "platform": "limitless",
        "base_url": settings.limitless_api_base,
        "api_available": True,
        "notes": "Limitless VGC public REST API, no auth required, rate-limited.",
    },
    {
        "platform": "labmaus",
        "base_url": settings.labmaus_base,
        "api_available": False,
        "notes": "React-rendered, requires Playwright. Contact: thelabmaus@gmail.com",
    },
    {
        "platform": "rk9",
        "base_url": settings.rk9_base,
        "api_available": False,
        "notes": "Official Play! Pokemon tournament platform. Server-rendered HTML.",
    },
    {
        "platform": "smogon",
        "base_url": settings.smogon_forum_base,
        "api_available": False,
        "notes": "XenForo forums, server-rendered. Tournament results + sample teams.",
    },
    {
        "platform": "youtube",
        "base_url": "https://www.googleapis.com/youtube/v3",
        "api_available": True,
        "notes": "YouTube Data API v3 via creator_registry table.",
    },
]


async def seed_sources() -> None:
    async with async_session_factory() as session:
        stmt = pg_insert(Source).values(SOURCES)
        stmt = stmt.on_conflict_do_nothing(index_elements=["platform"])
        await session.execute(stmt)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_sources())
