"""
Async SQLite persistence layer.

Provides two tables used as durable fallback caches:
  • active_drafts  — in-progress Draft objects (NCLP-002)
  • elo_ratings    — per-player ELO records   (NCLP-006)

All functions are async (aiosqlite).  Call ``init_db()`` once at startup
before using any other function.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from src.config import settings

log = logging.getLogger(__name__)

# Strip SQLAlchemy driver prefix so we get a plain filesystem path
# e.g. "sqlite+aiosqlite:///path/to/db" → "path/to/db"
_raw_url: str = settings.database_url
_DB_PATH: Path = Path(re.sub(r"^sqlite(?:\+\w+)?:///", "", _raw_url))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as conn:
        await conn.executescript("""
            CREATE TABLE IF NOT EXISTS active_drafts (
                guild_id   TEXT PRIMARY KEY,
                draft_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS elo_ratings (
                guild_id     TEXT NOT NULL,
                player_id    TEXT NOT NULL,
                elo          INTEGER NOT NULL DEFAULT 1000,
                wins         INTEGER NOT NULL DEFAULT 0,
                losses       INTEGER NOT NULL DEFAULT 0,
                streak       INTEGER NOT NULL DEFAULT 0,
                display_name TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL,
                PRIMARY KEY (guild_id, player_id)
            );
        """)
        await conn.commit()
    log.debug("SQLite tables initialised at %s", _DB_PATH)


# ── Draft persistence ─────────────────────────────────────────────────────────

async def save_draft(guild_id: str, draft_json: str) -> None:
    """Upsert a serialised Draft into active_drafts."""
    async with aiosqlite.connect(_DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO active_drafts (guild_id, draft_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                draft_json = excluded.draft_json,
                updated_at = excluded.updated_at
            """,
            (guild_id, draft_json, _now()),
        )
        await conn.commit()


async def delete_draft(guild_id: str) -> None:
    """Remove a completed/cancelled draft from active_drafts."""
    async with aiosqlite.connect(_DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM active_drafts WHERE guild_id = ?", (guild_id,)
        )
        await conn.commit()


async def load_all_drafts() -> list[tuple[str, str]]:
    """Return [(guild_id, draft_json), ...] for all rows in active_drafts."""
    async with aiosqlite.connect(_DB_PATH) as conn:
        async with conn.execute(
            "SELECT guild_id, draft_json FROM active_drafts"
        ) as cursor:
            return await cursor.fetchall()


# ── ELO persistence ───────────────────────────────────────────────────────────

async def save_elo(
    guild_id: str,
    player_id: str,
    elo: int,
    wins: int,
    losses: int,
    streak: int,
    display_name: str,
) -> None:
    """Upsert a player's ELO row."""
    async with aiosqlite.connect(_DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO elo_ratings
                (guild_id, player_id, elo, wins, losses, streak, display_name, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, player_id) DO UPDATE SET
                elo          = excluded.elo,
                wins         = excluded.wins,
                losses       = excluded.losses,
                streak       = excluded.streak,
                display_name = excluded.display_name,
                updated_at   = excluded.updated_at
            """,
            (guild_id, player_id, elo, wins, losses, streak, display_name, _now()),
        )
        await conn.commit()


async def load_all_elo() -> list[dict]:
    """Return all ELO rows as dicts."""
    async with aiosqlite.connect(_DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT guild_id, player_id, elo, wins, losses, streak, display_name "
            "FROM elo_ratings"
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(r) for r in rows]
