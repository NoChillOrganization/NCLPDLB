"""One description of each Source: Adapter, Route, normalizer, DB name, Ingest mode.

Every entry point (sync_all, sync_smogon, sync_pikalytics, sync_limitless_vgc,
sync_replays) goes through sync_source / run_standalone, so the CLI-key -> DB
source-name mapping and the Ingest mode rules live here once. Defaults are the
production values from .github/workflows/sync-prod.yml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg

from src.platform.normalize.replay import normalize_replay_row
from src.platform.normalize.tournament import normalize_tournament_row
from src.platform.normalize.usage import normalize_usage_row
from src.platform.orchestrate import (
    dry_run_normalize,
    land_and_normalize,
    with_ingest_run,
)
from src.platform.retry import retry_async
from src.platform.sources.limitless import LimitlessAdapter
from src.platform.sources.pikalytics import PikalyticsAdapter
from src.platform.sources.showdown import ShowdownAdapter
from src.platform.sources.smogon import SmogonAdapter
from src.platform.store.db import get_pool, migrate

# Production defaults (sync-prod.yml); every CLI shares them.
DEFAULT_CUTOFF = 1500
DEFAULT_REPLAY_PAGES = 5
DEFAULT_MIN_RATING = 1500


async def _replay_normalize(
    conn: asyncpg.Connection,
    *,
    raw_id: int,
    source: str,
    natural_key: str,  # noqa: ARG001  — not used by replay normalizer
    payload: dict,
) -> int:
    """Adapter: land_and_normalize passes natural_key; normalize_replay_row doesn't need it."""
    return await normalize_replay_row(
        conn, raw_id=raw_id, source=source, payload=payload
    )


@dataclass(frozen=True)
class SourceSpec:
    key: str  # CLI/branch name
    db_name: (
        str  # `source` table name (monitoring.py's stale-sync thresholds key on it)
    )
    route: str
    adapter: type
    normalize: Any
    ids_mode: str | None = None  # Ingest mode when explicit ids are given

    def mode(self, fetch_kwargs: dict) -> str:
        if self.ids_mode and fetch_kwargs.get("ids"):
            return self.ids_mode
        return "periodic"


# The `source` table (migrations/0001_init.sql) keys on DB names that don't always
# match the CLI key — "replays" is "showdown" in the DB. with_ingest_run resolves
# source_id via `SELECT id FROM source WHERE name = $1`, which silently no-ops
# (no DB error) on an unregistered name, so a wrong db_name lets ingest run fine
# while never recording a health row (the STALE_SYNC incident).
SOURCES: dict[str, SourceSpec] = {
    s.key: s
    for s in (
        SourceSpec("smogon", "smogon", "usage", SmogonAdapter, normalize_usage_row),
        SourceSpec(
            "pikalytics", "pikalytics", "usage", PikalyticsAdapter, normalize_usage_row
        ),
        SourceSpec(
            "limitless",
            "limitless",
            "tournament",
            LimitlessAdapter,
            normalize_tournament_row,
            ids_mode="event",
        ),
        SourceSpec(
            "replays",
            "showdown",
            "replay",
            ShowdownAdapter,
            _replay_normalize,
            ids_mode="replay_targeted",
        ),
    )
}


async def sync_source(
    spec: SourceSpec,
    conn: asyncpg.Connection | None,
    *,
    dry_run: bool = False,
    deadline: float | None = None,
    **fetch_kwargs: Any,
) -> dict:
    """Fetch (with retry), then dry-run validate or land+normalize in an ingest_run.

    conn may be None only when dry_run is True.
    """
    records = await retry_async(
        lambda: spec.adapter().fetch(**fetch_kwargs), deadline=deadline
    )
    if dry_run:
        return await dry_run_normalize(records)
    return await with_ingest_run(
        conn,
        source=spec.db_name,
        route=spec.route,
        mode=spec.mode(fetch_kwargs),
        fn=lambda: land_and_normalize(
            conn,
            source=spec.db_name,
            route=spec.route,
            records=records,
            normalize=spec.normalize,
        ),
    )


async def run_standalone(
    spec: SourceSpec, *, dry_run: bool = False, **fetch_kwargs: Any
) -> None:
    """Single-source CLI path: migrate/pool, print stats, exit 1 on dry-run errors."""
    if dry_run:
        stats = await sync_source(spec, None, dry_run=True, **fetch_kwargs)
        print("DRY RUN:", stats)
        if stats["errored"]:
            raise SystemExit(1)
        return
    await migrate()
    pool = await get_pool()
    async with pool.acquire() as conn:
        print(await sync_source(spec, conn, **fetch_kwargs))
