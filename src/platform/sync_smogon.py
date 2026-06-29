"""Periodic Smogon usage-stats sync.

Usage:
    python -m src.platform.sync_smogon \\
        --period 2026-05 \\
        --formats gen9vgc2025regi gen9ou \\
        --cutoff 1500

Fetches chaos JSON snapshots for each format+period+cutoff and lands them into
raw_ingest, then normalizes to usage_snapshot/usage_entry/usage_moveset.
Always runs in 'periodic' mode (no event or replay_targeted variant for Smogon).

# ponytail: shared loop + ingest_run wiring now live in orchestrate.py.
"""

from __future__ import annotations

import argparse
import asyncio

from src.platform.normalize.usage import normalize_usage_row
from src.platform.orchestrate import (
    dry_run_normalize,
    land_and_normalize,
    with_ingest_run,
)
from src.platform.sources.smogon import SmogonAdapter
from src.platform.store.db import get_pool, migrate


async def _run(
    *, period: str, formats: list[str], cutoff: int, dry_run: bool = False
) -> None:
    adapter = SmogonAdapter()
    records = await adapter.fetch(period=period, formats=formats, cutoff=cutoff)
    if dry_run:
        stats = await dry_run_normalize(records)
        print("DRY RUN:", stats)
        if stats["errored"]:
            raise SystemExit(1)
        return
    await migrate()
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await with_ingest_run(
            conn,
            source="smogon",
            route="usage",
            mode="periodic",
            fn=lambda: land_and_normalize(
                conn,
                source="smogon",
                route="usage",
                records=records,
                normalize=normalize_usage_row,
            ),
        )
    print(stats)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync_smogon", description=__doc__)
    parser.add_argument(
        "--period", required=True, metavar="YYYY-MM", help="Stats month, e.g. 2026-05"
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        required=True,
        metavar="FORMAT",
        help="Showdown format slugs to sync",
    )
    parser.add_argument(
        "--cutoff", type=int, default=1500, help="Elo cutoff tier (default 1500)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Fetch and validate without writing to DB",
    )
    args = parser.parse_args()
    asyncio.run(
        _run(
            period=args.period,
            formats=args.formats,
            cutoff=args.cutoff,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
