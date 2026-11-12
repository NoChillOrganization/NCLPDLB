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

from src.platform.source_spec import (
    DEFAULT_MIN_RATING,
    DEFAULT_REPLAY_PAGES,
    SOURCES,
    run_standalone,
)


async def _run(
    *,
    ids: list[str] | None,
    format: str | None,
    pages: int,
    min_rating: int,
    dry_run: bool = False,
) -> None:
    await run_standalone(
        SOURCES["replays"],
        dry_run=dry_run,
        ids=ids,
        format=format,
        pages=pages,
        min_rating=min_rating,
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync_replays", description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--ids",
        nargs="+",
        metavar="ID",
        help="Specific replay IDs (replay_targeted mode)",
    )
    group.add_argument(
        "--format",
        metavar="FORMAT",
        help="Showdown format slug for ladder sweep (periodic mode)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_REPLAY_PAGES,
        help="Max search pages for ladder sweep (default 5)",
    )
    parser.add_argument(
        "--min-rating",
        type=int,
        default=DEFAULT_MIN_RATING,
        dest="min_rating",
        help="Skip ladder replays below this rating (default 1500)",
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
            ids=args.ids,
            format=getattr(args, "format", None),
            pages=args.pages,
            min_rating=args.min_rating,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
