"""Celery app: task queue backbone. Beat drives periodic syncs; one queue per source."""

import logging

from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, task_retry

from config import settings

app = Celery("pokemon_pipeline", broker=settings.redis_url, backend=settings.redis_url)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    acks_late=True,
    task_soft_time_limit=300,
    task_time_limit=600,
    worker_concurrency=4,
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "tasks.ingest.limitless.*": {"queue": "limitless"},
        "tasks.ingest.labmaus.*": {"queue": "labmaus"},
        "tasks.ingest.rk9.*": {"queue": "rk9"},
        "tasks.ingest.smogon.*": {"queue": "smogon"},
        "tasks.ingest.youtube.*": {"queue": "youtube"},
        "tasks.process.*": {"queue": "processing"},
    },
    beat_schedule={
        "sync-limitless-daily": {
            "task": "tasks.ingest.limitless.sync_all_tournaments",
            "schedule": crontab(hour=6, minute=0),
        },
        "sync-labmaus-daily": {
            "task": "tasks.ingest.labmaus.sync_recent_tournaments",
            "schedule": crontab(hour=7, minute=0),
        },
        "sync-rk9-daily": {
            "task": "tasks.ingest.rk9.sync_recent_events",
            "schedule": crontab(hour=7, minute=30),
        },
        "sync-youtube-creators-weekly": {
            "task": "tasks.ingest.youtube.sync_all_creators",
            "schedule": crontab(day_of_week=1, hour=8, minute=0),
        },
        "sync-smogon-weekly": {
            "task": "tasks.ingest.smogon.sync_tournament_threads",
            "schedule": crontab(day_of_week=2, hour=8, minute=0),
        },
        "backfill-check": {
            "task": "tasks.process.check_pending_backfill.check_pending_backfill",
            "schedule": crontab(hour="*/4"),
        },
    },
)

# Discover tasks from ingest/process subpackages
app.autodiscover_tasks(["tasks.ingest", "tasks.process"], related_name=None, force=True)

logger = logging.getLogger(__name__)


@task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    logger.error(
        "task_failure",
        extra={"task": getattr(sender, "name", str(sender)), "task_id": task_id, "error": str(exception)},
    )


@task_retry.connect
def on_task_retry(sender=None, request=None, reason=None, **kwargs):
    retries = getattr(request, "retries", None) if request else None
    eta = getattr(request, "eta", None) if request else None
    logger.warning(
        "task_retry",
        extra={"task": getattr(sender, "name", str(sender)), "retries": retries, "eta": str(eta), "reason": str(reason)},
    )
