"""Shared ingest orchestration: run-tracking and land+normalize loop.

Two functions extracted from the 3× duplicated pattern in sync.py:

  land_and_normalize — iterates RawRecords, lands each, calls the normalizer
                        hook, returns {landed, normalized} stats.
  with_ingest_run    — wraps a coroutine fn() in an ingest_run DB row,
                       recording mode, timing, stats, and ok/error status.

Callers (sync_*.py entry points) pass source-specific adapters and normalizers
as callables so this module stays import-free of individual normalizers.
# ponytail: no scheduler here — these are manual/CI-invoked entry points;
#           wrap in systemd timers or GitHub Actions when periodic scheduling is needed.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Awaitable, Callable

import asyncpg

from src.platform.sources.base import RawRecord
from src.platform.store.repositories import land_raw


async def land_and_normalize(
    conn: asyncpg.Connection,
    *,
    source: str,
    route: str,
    records: Iterable[RawRecord],
    normalize: Callable[..., Awaitable[Any]],
) -> dict[str, int]:
    """Land each RawRecord into raw_ingest and call *normalize* for new payloads.

    Args:
        conn:      asyncpg connection (already acquired from the pool).
        source:    Source name matching a ``source.name`` row ('smogon', …).
        route:     Ingest route ('usage' | 'tournament' | 'replay').
        records:   Iterable of RawRecord emitted by a SourceAdapter.
        normalize: Async callable with signature
                   ``(conn, *, raw_id, source, natural_key, payload) -> Any``.
                   Called only for newly-landed records (land_raw returned an id).

    Returns:
        {'landed': int, 'normalized': int}
        ``landed`` counts every record processed (including dups);
        ``normalized`` counts records where the normalizer actually ran.
    """
    landed = normalized = 0
    for record in records:
        raw_id = await land_raw(
            conn,
            source=source,
            route=route,
            natural_key=record.natural_key,
            payload=record.payload,
            url=record.url,
        )
        landed += 1
        if raw_id is None:
            continue  # identical payload already in raw_ingest — idempotent skip
        await normalize(
            conn,
            raw_id=raw_id,
            source=source,
            natural_key=record.natural_key,
            payload=record.payload,
        )
        normalized += 1
    return {"landed": landed, "normalized": normalized}


async def with_ingest_run(
    conn: asyncpg.Connection,
    *,
    source: str,
    route: str,
    mode: str,
    fn: Callable[[], Awaitable[dict]],
) -> dict:
    """INSERT an ingest_run row, run *fn()*, then UPDATE with outcome.

    Args:
        conn:   asyncpg connection.
        source: Source name ('smogon' | 'pikalytics' | 'limitless' | 'showdown').
        route:  Must match ingest_run.route CHECK ('tournament' | 'usage' | 'replay').
        mode:   Must match ingest_run.mode CHECK
                ('periodic' | 'event' | 'replay_targeted').
        fn:     Async callable taking no arguments; should return a dict of stats
                (e.g. {'landed': N, 'normalized': M}) to store in ingest_run.stats.

    Returns:
        The dict returned by *fn()*, also written to ingest_run.stats.

    Raises:
        Whatever *fn()* raises; the ingest_run row is updated with status='error'
        and the exception message in stats before re-raising.
    """
    run_id: int = await conn.fetchval(
        """
        INSERT INTO ingest_run (source_id, route, mode)
        SELECT id, $2, $3 FROM source WHERE name = $1
        RETURNING id
        """,
        source, route, mode,
    )
    try:
        stats = await fn()
        await conn.execute(
            """
            UPDATE ingest_run
               SET status = 'ok', finished_at = now(), stats = $2::jsonb
             WHERE id = $1
            """,
            run_id, json.dumps(stats),
        )
        return stats
    except Exception as exc:
        await conn.execute(
            """
            UPDATE ingest_run
               SET status = 'error', finished_at = now(), stats = $2::jsonb
             WHERE id = $1
            """,
            run_id, json.dumps({"error": str(exc)}),
        )
        raise
