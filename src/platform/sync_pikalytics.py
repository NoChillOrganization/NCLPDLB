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

from src.platform.source_spec import SOURCES, run_standalone


async def _run(*, formats: list[str], max_pages: int, dry_run: bool = False) -> None:
    await run_standalone(
        SOURCES["pikalytics"], dry_run=dry_run, formats=formats, max_pages=max_pages
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync_pikalytics", description=__doc__)
    parser.add_argument(
        "--formats",
        nargs="+",
        required=True,
        metavar="FORMAT",
        help="Pikalytics format slugs to sync",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        dest="max_pages",
        help="Max pages to fetch per format (default 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Fetch and validate without writing to DB",
    )
    args = parser.parse_args()
    asyncio.run(
        _run(formats=args.formats, max_pages=args.max_pages, dry_run=args.dry_run)
    )


if __name__ == "__main__":
    main()
