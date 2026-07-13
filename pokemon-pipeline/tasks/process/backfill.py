"""Historical backfill orchestration — resumable, chunked, tracked in backfill_log."""

from __future__ import annotations

import logging

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from celery_app import app
from config import settings
from models.db import BackfillLog, async_session_factory
from tasks.utils import RateLimitedClient, date_filter

logger = logging.getLogger(__name__)

# Source -> callable that lists qualifying external tournament/event IDs for backfill seeding.
_LIST_FETCHERS = {}


def _register_list_fetcher(source: str):
    def decorator(fn):
        _LIST_FETCHERS[source] = fn
        return fn

    return decorator


@_register_list_fetcher("limitless")
async def _list_limitless(client: RateLimitedClient) -> list[str]:
    from tasks.ingest.limitless import fetch_tournaments

    ids: list[str] = []
    page = 1
    while True:
        batch = await fetch_tournaments(client, page)
        if not batch:
            break
        qualifying = [t for t in batch if date_filter(t.get("date"), settings.backfill_start_date)]
        if not qualifying and page > 1:
            break
        ids.extend(str(t["id"]) for t in qualifying)
        page += 1
    return ids


@_register_list_fetcher("rk9")
async def _list_rk9(client: RateLimitedClient) -> list[str]:
    from tasks.ingest.rk9 import scrape_event_list

    events = await scrape_event_list(client)
    return [str(e["id"]) for e in events]


# Source -> Celery task used to actually import one already-known external_id.
_SOURCE_SYNC_TASK_NAMES = {
    "limitless": "tasks.ingest.limitless.sync_single_tournament",
    "rk9": "tasks.ingest.rk9.sync_recent_events",  # RK9/LabMaus/Smogon/YouTube sync in
    "labmaus": "tasks.ingest.labmaus.sync_recent_tournaments",  # source-wide batches; single-id
    "smogon": "tasks.ingest.smogon.sync_tournament_threads",  # dispatch re-runs the whole batch,
    "youtube": "tasks.ingest.youtube.sync_all_creators",  # which is idempotent so safe to repeat.
}


async def populate_backfill_log(session: AsyncSession, source: str | None, start_date: str) -> int:
    """Fetch qualifying external IDs for source (or all sources) and insert as pending. Idempotent."""
    sources = [source] if source else list(_LIST_FETCHERS.keys())
    inserted = 0
    async with RateLimitedClient() as client:
        for src in sources:
            fetcher = _LIST_FETCHERS.get(src)
            if fetcher is None:
                logger.warning("No backfill list-fetcher registered for source=%s", src)
                continue
            external_ids = await fetcher(client)
            if not external_ids:
                continue
            stmt = pg_insert(BackfillLog).values(
                [{"source": src, "external_id": eid, "status": "pending"} for eid in external_ids]
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["source", "external_id"])
            result = await session.execute(stmt)
            inserted += result.rowcount or 0
        await session.commit()
    return inserted


@app.task(bind=True, name="tasks.process.backfill.sync_pending_backfill")
def sync_pending_backfill(self, source: str | None = None, batch_size: int = 50) -> dict:
    import asyncio

    return asyncio.run(_sync_pending_backfill(source, batch_size))


async def _sync_pending_backfill(source: str | None, batch_size: int) -> dict:
    processed = succeeded = failed = 0

    async with async_session_factory() as session:
        query = select(BackfillLog).where(BackfillLog.status == "pending")
        if source:
            query = query.where(BackfillLog.source == source)
        query = query.order_by(BackfillLog.id).limit(batch_size)
        rows = (await session.execute(query)).scalars().all()

        for row in rows:
            task_name = _SOURCE_SYNC_TASK_NAMES.get(row.source)
            processed += 1
            if task_name is None:
                await session.execute(
                    update(BackfillLog)
                    .where(BackfillLog.id == row.id)
                    .values(status="failed", error_message=f"no sync task for source={row.source}")
                )
                failed += 1
                continue
            try:
                # skip_validation=True maximizes backfill throughput; re-validate later via
                # /admin/validate/rerun. Only limitless's single-tournament task takes a
                # tournament_id; the other sources' tasks re-sync their whole batch (idempotent).
                if row.source == "limitless":
                    app.send_task(task_name, kwargs={"tournament_id": row.external_id, "skip_validation": True})
                else:
                    app.send_task(task_name)
                await session.execute(
                    update(BackfillLog).where(BackfillLog.id == row.id).values(status="done")
                )
                succeeded += 1
            except Exception as exc:  # noqa: BLE001 - one failure must not abort the batch
                logger.error("Backfill dispatch failed for %s/%s: %s", row.source, row.external_id, exc)
                await session.execute(
                    update(BackfillLog)
                    .where(BackfillLog.id == row.id)
                    .values(status="failed", error_message=str(exc))
                )
                failed += 1

        await session.commit()

    logger.info("backfill batch done: processed=%d succeeded=%d failed=%d", processed, succeeded, failed)
    return {"processed": processed, "succeeded": succeeded, "failed": failed}
