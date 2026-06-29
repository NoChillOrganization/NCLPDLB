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
import sys
import time
from collections.abc import Iterable
from typing import Any, Awaitable, Callable

import asyncpg

from src.platform.sources.base import RawRecord
from src.platform.store.repositories import land_raw, mark_raw_error, to_dead_letter


async def dry_run_normalize(records: Iterable[RawRecord]) -> dict[str, int]:
    """Validate adapter records in memory — no DB writes.

    Checks each RawRecord has a non-empty natural_key and non-empty payload.
    Returns the same stats shape as land_and_normalize for consistent dry-run output.
    Exits non-zero downstream if any record is malformed (parser regression gate).
    """
    fetched = normalized = errored = 0
    for rec in records:
        fetched += 1
        try:
            if not rec.natural_key:
                raise ValueError("empty natural_key")
            if not rec.payload:
                raise ValueError("empty payload")
            normalized += 1
        except Exception:
            errored += 1
    return {"fetched": fetched, "normalized": normalized, "errored": errored}


async def land_and_normalize(
    conn: asyncpg.Connection,
    *,
    source: str,
    route: str,
    records: Iterable[RawRecord],
    normalize: Callable[..., Awaitable[Any]],
    ingest_run_id: int | None = None,
) -> dict[str, int]:
    """Land each RawRecord into raw_ingest and call *normalize* for new payloads.

    Args:
        conn:          asyncpg connection (already acquired from the pool).
        source:        Source name matching a ``source.name`` row ('smogon', …).
        route:         Ingest route ('usage' | 'tournament' | 'replay').
        records:       Iterable of RawRecord emitted by a SourceAdapter.
        normalize:     Async callable with signature
                       ``(conn, *, raw_id, source, natural_key, payload) -> Any``.
                       Called only for newly-landed records (land_raw returned an id).
        ingest_run_id: Optional run id for dead-letter traceability.

    Returns:
        {'landed': int, 'normalized': int, 'errored': int}
        ``landed`` counts every record processed (including dups);
        ``normalized`` counts records where the normalizer actually ran;
        ``errored`` counts records that failed normalization (dead-lettered).
    """
    landed = normalized = errored = 0
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
        try:
            await normalize(
                conn,
                raw_id=raw_id,
                source=source,
                natural_key=record.natural_key,
                payload=record.payload,
            )
            normalized += 1
        except Exception as exc:  # parse / permanent failure — keep processing rest
            errored += 1
            await mark_raw_error(conn, raw_id=raw_id)
            await to_dead_letter(
                conn,
                source=source,
                route=route,
                natural_key=record.natural_key,
                payload=record.payload,
                error=f"{type(exc).__name__}: {exc}",
                ingest_run_id=ingest_run_id,
            )
    return {"landed": landed, "normalized": normalized, "errored": errored}


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
    t0 = time.monotonic()
    try:
        stats = await fn()
        duration = round(time.monotonic() - t0, 2)
        await conn.execute(
            """
            UPDATE ingest_run
               SET status = 'ok', finished_at = now(), stats = $2::jsonb
             WHERE id = $1
            """,
            run_id, json.dumps({**stats, "sync_duration_seconds": duration}),
        )
        print(json.dumps({
            "event": "ingest_run_ok", "source": source, "route": route, "mode": mode,
            "run_id": run_id, "duration_secs": duration, **stats,
        }), file=sys.stderr)
        return {**stats, "sync_duration_seconds": duration}
    except Exception as exc:
        duration = round(time.monotonic() - t0, 2)
        error_msg = f"{type(exc).__name__}: {exc}"
        await conn.execute(
            """
            UPDATE ingest_run
               SET status = 'error', finished_at = now(), stats = $2::jsonb
             WHERE id = $1
            """,
            run_id, json.dumps({"error": error_msg, "sync_duration_seconds": duration}),
        )
        print(json.dumps({
            "event": "ingest_run_error", "source": source, "route": route, "mode": mode,
            "run_id": run_id, "duration_secs": duration, "error": error_msg,
        }), file=sys.stderr)
        # Route exhausted/unrecoverable failures to dead_letter for operator review.
        # payload=None at run level — we don't have a single record to blame here.
        await to_dead_letter(
            conn,
            source=source,
            route=route,
            natural_key=None,
            payload=None,
            error=error_msg,
            ingest_run_id=run_id,
        )
        raise
