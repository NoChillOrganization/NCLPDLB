"""Admin endpoints — all require X-API-Key header. Import triggers, backfill control, stats."""

from __future__ import annotations

from datetime import datetime, timezone

from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, require_api_key
from api.schemas import ImportTriggerSchema, TaskStatusSchema
from celery_app import app as celery_app
from models.db import BackfillLog, Source, Team, Tournament

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_api_key)])

_SOURCE_SINGLE_TASK = {
    "limitless": "tasks.ingest.limitless.sync_single_tournament",
}
_SOURCE_BATCH_TASK = {
    "limitless": "tasks.ingest.limitless.sync_all_tournaments",
    "labmaus": "tasks.ingest.labmaus.sync_recent_tournaments",
    "rk9": "tasks.ingest.rk9.sync_recent_events",
    "smogon": "tasks.ingest.smogon.sync_tournament_threads",
    "youtube": "tasks.ingest.youtube.sync_all_creators",
}


@router.post("/import/tournament")
async def trigger_import(payload: ImportTriggerSchema) -> dict:
    if payload.source in _SOURCE_SINGLE_TASK:
        result = celery_app.send_task(
            _SOURCE_SINGLE_TASK[payload.source], kwargs={"tournament_id": payload.external_id}
        )
    else:
        # This source's ingest task syncs its whole batch (idempotent) rather than one ID.
        result = celery_app.send_task(_SOURCE_BATCH_TASK[payload.source])
    return {"task_id": result.id}


@router.get("/tasks/{task_id}", response_model=TaskStatusSchema)
async def get_task_status(task_id: str) -> TaskStatusSchema:
    result = AsyncResult(task_id, app=celery_app)
    return TaskStatusSchema(
        task_id=task_id,
        status=result.status,
        result=result.result if result.successful() else None,
        error=str(result.result) if result.failed() else None,
    )


@router.post("/backfill/start")
async def backfill_start(payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    from tasks.process.backfill import populate_backfill_log

    source = payload.get("source")
    start_date = payload.get("start_date", "2026-04-01")

    inserted = await populate_backfill_log(db, source, start_date)
    task = celery_app.send_task("tasks.process.backfill.sync_pending_backfill", kwargs={"source": source})

    pending_query = select(func.count()).select_from(BackfillLog).where(BackfillLog.status == "pending")
    if source:
        pending_query = pending_query.where(BackfillLog.source == source)
    pending_count = (await db.execute(pending_query)).scalar_one()

    return {
        "task_id": task.id,
        "pending_count": pending_count,
        "newly_inserted": inserted,
        "estimated_minutes": round(pending_count * 30 / 60, 1),
    }


@router.get("/backfill/status")
async def backfill_status(db: AsyncSession = Depends(get_db)) -> dict:
    counts_result = await db.execute(select(BackfillLog.status, func.count()).group_by(BackfillLog.status))
    counts = {status_: count for status_, count in counts_result.all()}
    total = sum(counts.values())
    done = counts.get("done", 0)
    pending = counts.get("pending", 0)
    failed = counts.get("failed", 0)

    failed_items_result = await db.execute(
        select(BackfillLog.source, BackfillLog.external_id, BackfillLog.error_message)
        .where(BackfillLog.status == "failed")
        .limit(50)
    )
    failed_items = [
        {"source": s, "external_id": e, "error": err} for s, e, err in failed_items_result.all()
    ]

    return {
        "total": total,
        "done": done,
        "pending": pending,
        "failed": failed,
        "percent_complete": round((done + failed) / total * 100, 1) if total else 100.0,
        "failed_items": failed_items,
    }


@router.post("/backfill/retry-failed")
async def backfill_retry_failed(db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        update(BackfillLog)
        .where(BackfillLog.status == "failed")
        .values(status="pending", error_message=None)
    )
    await db.commit()
    task = celery_app.send_task("tasks.process.backfill.sync_pending_backfill")
    return {"reset_count": result.rowcount or 0, "task_id": task.id}


@router.post("/validate/rerun")
async def validate_rerun() -> dict:
    task = celery_app.send_task("tasks.process.validator.revalidate_invalid_teams")
    return {"task_id": task.id}


@router.get("/stats")
async def pipeline_stats(db: AsyncSession = Depends(get_db)) -> dict:
    total_teams = (await db.execute(select(func.count()).select_from(Team))).scalar_one()

    per_source_result = await db.execute(
        select(Source.platform, func.count(Tournament.id))
        .join(Tournament, Tournament.source_id == Source.id, isouter=True)
        .group_by(Source.platform)
    )
    per_source = {platform: count for platform, count in per_source_result.all()}

    return {
        "total_teams": total_teams,
        "per_source_tournament_counts": per_source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
