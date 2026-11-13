"""Multi-source orchestrator: run all (or selected) sources in one command.

Combines the deadline logic from legacy sync.py with the per-source ingest_run
tracking and dead-letter routing from sync_*.py entry points.

Usage:
    # All sources (default)
    python -m src.platform.sync_all

    # Specific sources, custom deadline
    python -m src.platform.sync_all --sources smogon pikalytics --deadline-seconds 600

    # Daily data
    python -m src.platform.sync_all --sources limitless replays

    # Dry-run validation (no DB writes)
    python -m src.platform.sync_all --dry-run

Sources run sequentially so each uses a shrinking share of the deadline budget;
one source failing does not abort the rest (per-source try/except).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import asyncpg

from src.platform.source_spec import (
    DEFAULT_CUTOFF,
    DEFAULT_MIN_RATING,
    DEFAULT_REPLAY_PAGES,
    SOURCES,
    sync_source,
)
from src.platform.store.db import get_pool, migrate

ALL_SOURCES = ("smogon", "pikalytics", "limitless", "replays")


async def _run_source(
    conn: asyncpg.Connection,
    *,
    source: str,
    args: argparse.Namespace,
    deadline: float | None,
    dry_run: bool,
) -> dict:
    if source == "smogon":
        kw = {
            "period": args.period or _last_month(),
            "formats": args.formats,
            "cutoff": args.cutoff,
        }
    elif source == "pikalytics":
        kw = {"formats": args.formats}
    elif source == "limitless":
        kw = {"ids": None, "game": args.game, "limit": args.limit, "page": 1}
    elif source == "replays":
        kw = {
            "ids": None,
            "format": args.replay_format,
            "pages": args.pages,
            "min_rating": args.min_rating,
        }
    else:
        raise ValueError(f"unknown source: {source!r}")
    return await sync_source(
        SOURCES[source], conn, dry_run=dry_run, deadline=deadline, **kw
    )


def _last_month() -> str:
    """YYYY-MM for the last completed calendar month."""
    from datetime import date, timedelta

    d = date.today().replace(day=1) - timedelta(days=1)
    return d.strftime("%Y-%m")


async def _run(args: argparse.Namespace) -> int:
    sources = list(ALL_SOURCES) if "all" in args.sources else args.sources
    deadline = (
        time.monotonic() + args.deadline_seconds if args.deadline_seconds > 0 else None
    )
    dry_run = args.dry_run
    errors: list[str] = []

    try:
        if not dry_run:
            await migrate()
        pool = await get_pool()
    except (OSError, asyncpg.PostgresError) as exc:
        print(f"[db] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    for source in sources:
        async with pool.acquire() as conn:
            try:
                stats = await _run_source(
                    conn, source=source, args=args, deadline=deadline, dry_run=dry_run
                )
                print(
                    f"[{source}] {'DRY RUN ' if dry_run else ''}ok: {stats}",
                    file=sys.stderr,
                )
                if dry_run and stats["errored"]:
                    raise RuntimeError(f"{stats['errored']} record(s) errored")
            except Exception as exc:
                msg = f"[{source}] FAILED: {type(exc).__name__}: {exc}"
                print(msg, file=sys.stderr)
                errors.append(msg)

    if errors:
        print("\nERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync_all", description=__doc__)
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=[*ALL_SOURCES, "all"],
        default=["all"],
        help="Sources to sync (default: all)",
    )
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=300.0,
        dest="deadline_seconds",
        help="Wall-clock budget in seconds shared across all sources (0 = no limit)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Fetch and validate without DB writes",
    )
    # Usage-source args
    parser.add_argument(
        "--period",
        metavar="YYYY-MM",
        help="Month for Smogon stats (default: last completed month)",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["gen9championsvgc2026regmb", "gen9ou"],
        help="Format slugs for usage sources",
    )
    parser.add_argument(
        "--cutoff", type=int, default=DEFAULT_CUTOFF, help="Smogon ELO cutoff"
    )
    # Replay args
    parser.add_argument(
        "--replay-format",
        default="gen9championsvgc2026regmb",
        dest="replay_format",
        help="Showdown format for replay sweep",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=DEFAULT_REPLAY_PAGES,
        help="Max search pages for replay sweep",
    )
    parser.add_argument(
        "--min-rating",
        type=int,
        default=DEFAULT_MIN_RATING,
        dest="min_rating",
        help="Skip replays below this rating",
    )
    # Tournament args
    parser.add_argument("--game", default="VGC", help="Game filter for Limitless sweep")
    parser.add_argument(
        "--limit", type=int, default=50, help="Max tournaments per sweep"
    )
    args = parser.parse_args()
    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
