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

from src.platform.source_spec import DEFAULT_CUTOFF, SOURCES, run_standalone


async def _run(
    *, period: str, formats: list[str], cutoff: int, dry_run: bool = False
) -> None:
    await run_standalone(
        SOURCES["smogon"],
        dry_run=dry_run,
        period=period,
        formats=formats,
        cutoff=cutoff,
    )


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
        "--cutoff",
        type=int,
        default=DEFAULT_CUTOFF,
        help="Elo cutoff tier (default 1500)",
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
