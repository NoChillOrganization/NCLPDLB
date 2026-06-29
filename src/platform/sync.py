"""CLI entrypoint: python -m src.platform.sync <seed|replays|usage|event> ...
# ponytail: event mode is polling-only (--ids / --limit/--page discovery). Limitless also offers
# webhooks for push updates on finished tournaments — not wired; add when push is actually needed.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from src.platform.normalize.replay import normalize_replay_row
from src.platform.normalize.tournament import normalize_tournament_row
from src.platform.normalize.usage import normalize_usage_row
from src.platform.retry import retry_async
from src.platform.seed import seed_species
from src.platform.sources.limitless import LimitlessAdapter
from src.platform.sources.pikalytics import PikalyticsAdapter
from src.platform.sources.showdown import ShowdownAdapter
from src.platform.sources.smogon import SmogonAdapter
from src.platform.store.db import get_pool, migrate
from src.platform.store.repositories import land_raw


async def run_seed() -> None:
    await migrate()
    pool = await get_pool()
    async with pool.acquire() as conn:
        counts = await seed_species(conn)
    print(counts)


async def run_replays(ids: list[str], *, deadline: float | None = None) -> None:
    await migrate()
    pool = await get_pool()
    records = await retry_async(
        lambda: ShowdownAdapter().fetch(ids=ids),
        deadline=deadline,
    )
    async with pool.acquire() as conn:
        for record in records:
            raw_id = await land_raw(
                conn,
                source="showdown",
                route=record.route,
                natural_key=record.natural_key,
                payload=record.payload,
                url=record.url,
            )
            if raw_id is None:
                continue  # identical payload already landed
            await normalize_replay_row(
                conn, raw_id=raw_id, source="showdown", payload=record.payload
            )
    print(f"fetched={len(list(ids))} landed_and_normalized={len(records)}")


async def run_usage(
    *, period: str, formats: list[str], cutoff: int, deadline: float | None = None
) -> None:
    """Periodic mode: pull current usage snapshots from Smogon + Pikalytics."""
    await migrate()
    pool = await get_pool()
    landed = normalized = 0
    async with pool.acquire() as conn:
        for adapter in (SmogonAdapter(), PikalyticsAdapter()):
            kwargs = (
                {"period": period, "formats": formats, "cutoff": cutoff}
                if adapter.source == "smogon"
                else {"formats": formats}
            )
            records = await retry_async(
                lambda: adapter.fetch(**kwargs),
                deadline=deadline,
            )
            for record in records:
                raw_id = await land_raw(
                    conn,
                    source=adapter.source,
                    route=record.route,
                    natural_key=record.natural_key,
                    payload=record.payload,
                    url=record.url,
                )
                landed += 1
                if raw_id is None:
                    continue
                await normalize_usage_row(
                    conn,
                    raw_id=raw_id,
                    source=adapter.source,
                    natural_key=record.natural_key,
                    payload=record.payload,
                )
                normalized += 1
    print(f"landed={landed} normalized={normalized}")


async def run_event(
    *,
    ids: list[str] | None,
    game: str,
    limit: int,
    page: int,
    deadline: float | None = None,
) -> None:
    """Periodic/manual mode: pull tournament standings+decklists from Limitless."""
    await migrate()
    pool = await get_pool()
    landed = normalized = 0
    async with pool.acquire() as conn:
        records = await retry_async(
            lambda: LimitlessAdapter().fetch(
                ids=ids, game=game, limit=limit, page=page
            ),
            deadline=deadline,
        )
        for record in records:
            raw_id = await land_raw(
                conn,
                source="limitless",
                route=record.route,
                natural_key=record.natural_key,
                payload=record.payload,
                url=record.url,
            )
            landed += 1
            if raw_id is None:
                continue
            await normalize_tournament_row(
                conn,
                raw_id=raw_id,
                source="limitless",
                natural_key=record.natural_key,
                payload=record.payload,
            )
            normalized += 1
    print(f"landed={landed} normalized={normalized}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="sync")
    parser.add_argument(
        "--deadline-seconds",
        type=float,
        default=300.0,
        help="Wall-clock budget for the whole job in seconds (default: 300). "
        "0 = no deadline.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    replays_parser = sub.add_parser("replays")
    replays_parser.add_argument("--ids", nargs="+", required=True)

    usage_parser = sub.add_parser("usage")
    usage_parser.add_argument(
        "--period", required=True, help="YYYY-MM, used by Smogon only"
    )
    usage_parser.add_argument("--formats", nargs="+", required=True)
    usage_parser.add_argument("--cutoff", type=int, default=1500)

    event_parser = sub.add_parser("event")
    event_parser.add_argument(
        "--ids", nargs="+", help="specific Limitless tournament ids"
    )
    event_parser.add_argument("--game", default="VGC")
    event_parser.add_argument("--limit", type=int, default=50)
    event_parser.add_argument("--page", type=int, default=1)

    args = parser.parse_args()
    # deadline=None means no cap; 0 from CLI also maps to None (disabled).
    deadline = (
        (time.monotonic() + args.deadline_seconds)
        if args.deadline_seconds > 0
        else None
    )

    if args.cmd == "seed":
        asyncio.run(run_seed())
    elif args.cmd == "replays":
        asyncio.run(run_replays(args.ids, deadline=deadline))
    elif args.cmd == "usage":
        asyncio.run(
            run_usage(
                period=args.period,
                formats=args.formats,
                cutoff=args.cutoff,
                deadline=deadline,
            )
        )
    elif args.cmd == "event":
        asyncio.run(
            run_event(
                ids=args.ids,
                game=args.game,
                limit=args.limit,
                page=args.page,
                deadline=deadline,
            )
        )


if __name__ == "__main__":
    main()
