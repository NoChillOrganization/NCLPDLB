"""Seed creator_registry with known top VGC creators active in 2026. Idempotent."""

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert

from models.db import CreatorRegistry, async_session_factory

# Default regex matches any pokepast.es URL. Creator-specific patterns override when a
# creator consistently labels their paste ("Team Paste:", "My Team:", "Rental Code:").
_DEFAULT_PASTE_REGEX = r"https?://pokepast\.es/[a-f0-9]+"

CREATORS = [
    {
        "name": "WolfeyVGC",
        "youtube_channel_id": "UC_TODO_WOLFEY",  # TODO: confirm real channel ID
        "twitter_handle": "@WolfeyVGC",
        "description_paste_regex": r"(?:Team Paste|Rental Code):\s*(https?://pokepast\.es/[a-f0-9]+)",
        "is_active": True,
    },
    {
        "name": "Cybertron (Aaron Zheng)",
        "youtube_channel_id": "UC_TODO_CYBERTRON",  # TODO: confirm real channel ID
        "twitter_handle": "@cybertron_vgc",
        "description_paste_regex": _DEFAULT_PASTE_REGEX,
        "is_active": True,
    },
    {
        "name": "Popos VGC",
        "youtube_channel_id": "UC_TODO_POPOS",  # TODO: confirm real channel ID
        "twitter_handle": "@PoposVGC",
        "description_paste_regex": r"My Team:\s*(https?://pokepast\.es/[a-f0-9]+)",
        "is_active": True,
    },
    {
        "name": "CloverBells",
        "youtube_channel_id": "UC_TODO_CLOVERBELLS",  # TODO: confirm real channel ID
        "twitter_handle": "@CloverBellsVGC",
        "description_paste_regex": _DEFAULT_PASTE_REGEX,
        "is_active": True,
    },
    {
        "name": "Camron Ghorashi",
        "youtube_channel_id": "UC_TODO_CAMRON",  # TODO: confirm real channel ID
        "twitter_handle": "@CamGhorashi",
        "description_paste_regex": _DEFAULT_PASTE_REGEX,
        "is_active": True,
    },
    {
        "name": "Trainer Tube",
        "youtube_channel_id": "UC_TODO_TRAINERTUBE",  # TODO: confirm real channel ID
        "twitter_handle": None,
        "description_paste_regex": _DEFAULT_PASTE_REGEX,
        "is_active": True,
    },
    {
        "name": "Gulliman",
        "youtube_channel_id": "UC_TODO_GULLIMAN",  # TODO: confirm real channel ID
        "twitter_handle": "@GullimanVGC",
        "description_paste_regex": _DEFAULT_PASTE_REGEX,
        "is_active": True,
    },
    {
        "name": "Melon VGC",
        "youtube_channel_id": "UC_TODO_MELON",  # TODO: confirm real channel ID
        "twitter_handle": None,
        "description_paste_regex": _DEFAULT_PASTE_REGEX,
        "is_active": True,
    },
]


async def seed_creators() -> None:
    async with async_session_factory() as session:
        stmt = pg_insert(CreatorRegistry).values(CREATORS)
        stmt = stmt.on_conflict_do_nothing(index_elements=["name"])
        await session.execute(stmt)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_creators())
