"""Limitless VGC tournament sync — periodic sweep or targeted by ID.

Usage:
    # Periodic: sweep recent VGC tournaments
    python -m src.platform.sync_limitless_vgc --game VGC --limit 50 --page 1

    # Event: sync specific tournament IDs
    python -m src.platform.sync_limitless_vgc --ids abc123 def456

Fetches standings + decklists from the Limitless public API and lands them into
raw_ingest, then normalizes to tournament_event/tournament_team/tournament_team_member.

Mode is 'event' when --ids is supplied, 'periodic' otherwise.

# ponytail: shared loop + ingest_run wiring now live in orchestrate.py.
"""
from __future__ import annotations

import argparse
import asyncio

from src.platform.normalize.tournament import normalize_tournament_row
from src.platform.orchestrate import dry_run_normalize, land_and_normalize, with_ingest_run
from src.platform.sources.limitless import LimitlessAdapter
from src.platform.store.db import get_pool, migrate


async def _run(*, ids: list[str] | None, game: str, limit: int, page: int, dry_run: bool = False) -> None:
    mode = "event" if ids else "periodic"
    adapter = LimitlessAdapter()
    records = await adapter.fetch(ids=ids, game=game, limit=limit, page=page)
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
            source="limitless",
            route="tournament",
            mode=mode,
            fn=lambda: land_and_normalize(
                conn,
                source="limitless",
                route="tournament",
                records=records,
                normalize=normalize_tournament_row,
            ),
        )
    print(stats)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync_limitless_vgc", description=__doc__)
    parser.add_argument("--ids", nargs="+", metavar="ID",
                        help="Specific Limitless tournament IDs (event mode)")
    parser.add_argument("--game", default="VGC", help="Game filter for sweep (default VGC)")
    parser.add_argument("--limit", type=int, default=50, help="Max tournaments per sweep page")
    parser.add_argument("--page", type=int, default=1, help="Sweep page number (default 1)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Fetch and validate without writing to DB")
    args = parser.parse_args()
    asyncio.run(_run(ids=args.ids, game=args.game, limit=args.limit, page=args.page, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
