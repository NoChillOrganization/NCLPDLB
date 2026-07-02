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

ALL_SOURCES = ("smogon", "pikalytics", "limitless", "replays")


async def _replay_normalize(
    conn: asyncpg.Connection,
    *,
    raw_id: int,
    source: str,
    natural_key: str,  # noqa: ARG001
    payload: dict,
) -> int:
    return await normalize_replay_row(
        conn, raw_id=raw_id, source=source, payload=payload
    )


async def _run_source(
    conn: asyncpg.Connection,
    *,
    source: str,
    args: argparse.Namespace,
    deadline: float | None,
    dry_run: bool,
) -> dict:
    if source == "smogon":
        period = args.period or _last_month()
        records = await retry_async(
            lambda: SmogonAdapter().fetch(
                period=period,
                formats=args.formats,
                cutoff=args.cutoff,
            ),
            deadline=deadline,
        )
        mode = "periodic"
        normalize = normalize_usage_row
        route = "usage"
    elif source == "pikalytics":
        records = await retry_async(
            lambda: PikalyticsAdapter().fetch(formats=args.formats),
            deadline=deadline,
        )
        mode = "periodic"
        normalize = normalize_usage_row
        route = "usage"
    elif source == "limitless":
        records = await retry_async(
            lambda: LimitlessAdapter().fetch(
                ids=None, game=args.game, limit=args.limit, page=1
            ),
            deadline=deadline,
        )
        mode = "periodic"
        normalize = normalize_tournament_row
        route = "tournament"
    elif source == "replays":
        records = await retry_async(
            lambda: ShowdownAdapter().fetch(
                ids=None,
                format=args.replay_format,
                pages=args.pages,
                min_rating=args.min_rating,
            ),
            deadline=deadline,
        )
        mode = "periodic"
        normalize = _replay_normalize
        route = "replay"
    else:
        raise ValueError(f"unknown source: {source!r}")

    if dry_run:
        stats = await dry_run_normalize(records)
        return stats

    return await with_ingest_run(
        conn,
        source=source if source != "pikalytics" else "pikalytics",
        route=route,
        mode=mode,
        fn=lambda: land_and_normalize(
            conn,
            source=source if source not in ("smogon", "pikalytics") else source,
            route=route,
            records=records,
            normalize=normalize,
        ),
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

    if not dry_run:
        await migrate()

    pool = await get_pool()
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
    parser.add_argument("--cutoff", type=int, default=1500, help="Smogon ELO cutoff")
    # Replay args
    parser.add_argument(
        "--replay-format",
        default="gen9championsvgc2026regmb",
        dest="replay_format",
        help="Showdown format for replay sweep",
    )
    parser.add_argument(
        "--pages", type=int, default=5, help="Max search pages for replay sweep"
    )
    parser.add_argument(
        "--min-rating",
        type=int,
        default=1500,
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
