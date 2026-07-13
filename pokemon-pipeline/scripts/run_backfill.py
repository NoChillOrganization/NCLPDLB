#!/usr/bin/env python
"""Standalone CLI backfill runner — connects directly to the DB, no Docker required.

Usage:
    python scripts/run_backfill.py --source limitless --start-date 2026-04-01
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from sqlalchemy import func, select

from models.db import BackfillLog, async_session_factory
from tasks.process.backfill import populate_backfill_log, _sync_pending_backfill


async def _progress_snapshot(source: str | None) -> dict:
    async with async_session_factory() as session:
        query = select(BackfillLog.status, func.count()).group_by(BackfillLog.status)
        if source:
            query = query.where(BackfillLog.source == source)
        rows = (await session.execute(query)).all()
        counts = {status: count for status, count in rows}
    return counts


async def main(source: str | None, start_date: str) -> None:
    print(f"Populating backfill_log for source={source or 'ALL'} start_date={start_date} ...")
    async with async_session_factory() as session:
        inserted = await populate_backfill_log(session, source, start_date)
    print(f"Inserted {inserted} new pending rows (existing rows untouched).")

    while True:
        counts = await _progress_snapshot(source)
        pending = counts.get("pending", 0)
        done = counts.get("done", 0)
        failed = counts.get("failed", 0)
        total = pending + done + failed
        pct = (done + failed) / total * 100 if total else 100.0
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(f"\r[{bar}] {pct:5.1f}%  done={done} failed={failed} pending={pending}", end="", flush=True)

        if pending == 0:
            print()
            break

        result = await _sync_pending_backfill(source, batch_size=50)
        if result["processed"] == 0:
            time.sleep(10)
        time.sleep(10)

    print("Backfill complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=None, help="Limit to one source (limitless/labmaus/rk9/smogon/youtube)")
    parser.add_argument("--start-date", default="2026-04-01")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.source, args.start_date))
    except KeyboardInterrupt:
        print("\nInterrupted — safe to resume, backfill_log tracks progress.")
        sys.exit(1)
