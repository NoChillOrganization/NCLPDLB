"""Periodic Pikalytics usage-stats sync.

Usage:
    python -m src.platform.sync_pikalytics \\
        --formats gen9vgc2025regi \\
        --max-pages 10

Fetches paginated lead entries from Pikalytics for each format and lands them
into raw_ingest, then normalizes to usage_snapshot/usage_entry.
Always runs in 'periodic' mode.

# ponytail: shared loop + ingest_run wiring now live in orchestrate.py.
"""
from __future__ import annotations

import argparse
import asyncio

from src.platform.normalize.usage import normalize_usage_row
from src.platform.orchestrate import land_and_normalize, with_ingest_run
from src.platform.sources.pikalytics import PikalyticsAdapter
from src.platform.store.db import get_pool, migrate


async def _run(*, formats: list[str], max_pages: int) -> None:
    await migrate()
    pool = await get_pool()
    adapter = PikalyticsAdapter()
    records = await adapter.fetch(formats=formats, max_pages=max_pages)
    async with pool.acquire() as conn:
        stats = await with_ingest_run(
            conn,
            source="pikalytics",
            route="usage",
            mode="periodic",
            fn=lambda: land_and_normalize(
                conn,
                source="pikalytics",
                route="usage",
                records=records,
                normalize=normalize_usage_row,
            ),
        )
    print(stats)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync_pikalytics", description=__doc__)
    parser.add_argument("--formats", nargs="+", required=True, metavar="FORMAT",
                        help="Pikalytics format slugs to sync")
    parser.add_argument("--max-pages", type=int, default=10, dest="max_pages",
                        help="Max pages to fetch per format (default 10)")
    args = parser.parse_args()
    asyncio.run(_run(formats=args.formats, max_pages=args.max_pages))


if __name__ == "__main__":
    main()
