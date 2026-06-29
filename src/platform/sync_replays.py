"""Showdown replay sync — replay-targeted by ID or periodic ladder discovery.

Usage:
    # replay_targeted: fetch specific replays by ID
    python -m src.platform.sync_replays --ids gen9vgc2025regi-1234 gen9vgc2025regi-5678

    # periodic: discover recent ladder replays for a format
    python -m src.platform.sync_replays --format gen9vgc2025regi --pages 5 --min-rating 1500

Exactly one of --ids or --format is required.

Mode is 'replay_targeted' when --ids is supplied, 'periodic' for ladder discovery.

# ponytail: shared loop + ingest_run wiring now live in orchestrate.py.
#           normalize_replay_row doesn't take natural_key — wrapped below.
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg

from src.platform.normalize.replay import normalize_replay_row
from src.platform.orchestrate import land_and_normalize, with_ingest_run
from src.platform.sources.showdown import ShowdownAdapter
from src.platform.store.db import get_pool, migrate


async def _replay_normalize(
    conn: asyncpg.Connection,
    *,
    raw_id: int,
    source: str,
    natural_key: str,  # noqa: ARG001  — not used by replay normalizer
    payload: dict,
) -> int:
    """Adapter: land_and_normalize passes natural_key; normalize_replay_row doesn't need it."""
    return await normalize_replay_row(conn, raw_id=raw_id, source=source, payload=payload)


async def _run(
    *,
    ids: list[str] | None,
    format: str | None,
    pages: int,
    min_rating: int,
) -> None:
    mode = "replay_targeted" if ids else "periodic"
    await migrate()
    pool = await get_pool()
    adapter = ShowdownAdapter()
    records = await adapter.fetch(ids=ids, format=format, pages=pages, min_rating=min_rating)
    async with pool.acquire() as conn:
        stats = await with_ingest_run(
            conn,
            source="showdown",
            route="replay",
            mode=mode,
            fn=lambda: land_and_normalize(
                conn,
                source="showdown",
                route="replay",
                records=records,
                normalize=_replay_normalize,
            ),
        )
    print(stats)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync_replays", description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ids", nargs="+", metavar="ID",
                       help="Specific replay IDs (replay_targeted mode)")
    group.add_argument("--format", metavar="FORMAT",
                       help="Showdown format slug for ladder sweep (periodic mode)")
    parser.add_argument("--pages", type=int, default=10,
                        help="Max search pages for ladder sweep (default 10)")
    parser.add_argument("--min-rating", type=int, default=0, dest="min_rating",
                        help="Skip ladder replays below this rating (default 0)")
    args = parser.parse_args()
    asyncio.run(_run(
        ids=args.ids,
        format=getattr(args, "format", None),
        pages=args.pages,
        min_rating=args.min_rating,
    ))


if __name__ == "__main__":
    main()
