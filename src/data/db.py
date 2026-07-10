"""
Async SQLite persistence layer.

Provides two tables used as durable fallback caches:
  • active_drafts  — in-progress Draft objects (NCLP-002)
  • elo_ratings    — per-player ELO records   (NCLP-006)

All functions are async (aiosqlite).  Call ``init_db()`` once at startup
before using any other function.  Call ``close_db()`` on bot shutdown to
release the connection cleanly.

Connection strategy (M19):
  A single long-lived aiosqlite.Connection is shared across all calls.
  A module-level asyncio.Lock guards each write transaction so that
  concurrent coroutines cannot interleave execute + commit pairs.
  WAL journal mode is applied once at init and persists at the DB-file
  level, allowing reads during writes.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from src.config import settings

log = logging.getLogger(__name__)

# Strip SQLAlchemy driver prefix so we get a plain filesystem path
# e.g. "sqlite+aiosqlite:///path/to/db" → "path/to/db"
_raw_url: str = settings.database_url
_DB_PATH: Path = Path(re.sub(r"^sqlite(?:\+\w+)?:///", "", _raw_url))

# ── Shared connection state ───────────────────────────────────────────────────

_conn: Optional[aiosqlite.Connection] = None
_conn_loop: Optional[asyncio.AbstractEventLoop] = None  # loop the conn is bound to
_open_lock: asyncio.Lock = asyncio.Lock()  # serialise lazy-open races
_write_lock: asyncio.Lock = asyncio.Lock()  # serialise execute+commit pairs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_conn() -> aiosqlite.Connection:
    """Return the shared connection, opening it lazily if needed.

    aiosqlite binds a connection (and its worker thread) to the event loop that
    was running when it opened. Reusing it from a *different* loop deadlocks: the
    worker calls ``call_soon_threadsafe`` on the old (often closed) loop, so the
    future on the current loop is never resolved and the await hangs. Python 3.14
    made the closed-loop check strict, turning this into a hard failure. Guard by
    reopening whenever the running loop changed (prod uses one long-lived loop, so
    this only fires under per-test event loops or a loop restart).
    """
    global _conn, _conn_loop, _open_lock
    running = asyncio.get_running_loop()
    if _conn is not None and _conn_loop is running:
        return _conn
    async with _open_lock:
        if _conn is not None and _conn_loop is not running:
            # Bound to a stale loop — abandon it. Do NOT await close(): a
            # cross-loop close reproduces the same hang. Drop the reference and
            # let the orphaned worker thread unwind on its own.
            log.warning("aiosqlite connection loop changed; reopening (M19)")
            _conn = None
            _conn_loop = None
            # asyncio.Lock binds its loop lazily on first *contended* acquire
            # (see asyncio.mixins._LoopBoundMixin) and raises RuntimeError if a
            # later contended acquire runs on a different loop. Reassigning here
            # is safe: this `async with` already holds a reference to the old
            # lock object, so __aexit__ still releases it correctly; only future
            # callers see the fresh, unbound lock.
            _open_lock = asyncio.Lock()
        if _conn is None:  # double-checked after acquiring lock
            _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = await aiosqlite.connect(_DB_PATH)
            _conn.row_factory = aiosqlite.Row
            await _conn.execute("PRAGMA journal_mode=WAL")
            await _conn.commit()
            _conn_loop = running
            log.debug("aiosqlite connection opened at %s (M19)", _DB_PATH)
    return _conn


# ── Lifecycle ─────────────────────────────────────────────────────────────────


async def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    conn = await _get_conn()
    async with _write_lock:
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


async def close_db() -> None:
    """Close the shared connection. Call once on bot shutdown."""
    global _conn, _conn_loop, _open_lock
    if _conn is None:
        return
    async with _open_lock:
        if _conn is not None:
            await _conn.close()
            _conn = None
            _conn_loop = None
            # See the matching comment in _get_conn(): recreate the lock so a
            # future contended acquire (e.g. from a test on a new event loop)
            # doesn't hit a RuntimeError from _LoopBoundMixin binding to this
            # loop. This is the path tests actually exercise: the conftest
            # teardown fixture calls close_db() every test, nulling _conn
            # before the next test's _get_conn() ever sees it.
            _open_lock = asyncio.Lock()
            log.debug("aiosqlite connection closed (M19)")


# ── Draft persistence ─────────────────────────────────────────────────────────


async def save_draft(guild_id: str, draft_json: str) -> None:
    """Upsert a serialised Draft into active_drafts."""
    conn = await _get_conn()
    async with _write_lock:
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
    conn = await _get_conn()
    async with _write_lock:
        await conn.execute("DELETE FROM active_drafts WHERE guild_id = ?", (guild_id,))
        await conn.commit()


async def load_all_drafts() -> list[tuple[str, str]]:
    """Return [(guild_id, draft_json), ...] for all rows in active_drafts."""
    conn = await _get_conn()
    async with conn.execute("SELECT guild_id, draft_json FROM active_drafts") as cursor:
        rows = await cursor.fetchall()
    # aiosqlite.Row supports index access, so callers receive compatible tuples
    return [(r[0], r[1]) for r in rows]


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
    conn = await _get_conn()
    async with _write_lock:
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
    conn = await _get_conn()
    conn.row_factory = aiosqlite.Row
    async with conn.execute(
        "SELECT guild_id, player_id, elo, wins, losses, streak, display_name "
        "FROM elo_ratings"
    ) as cursor:
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]
