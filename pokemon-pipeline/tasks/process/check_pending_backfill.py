"""Beat-scheduled task: pick up pending backfill_log rows and dispatch per-source ingest tasks.

Thin wrapper around tasks.process.backfill.sync_pending_backfill (the full implementation,
added in Phase 2) so the Beat schedule configured in celery_app.py has a stable task name from
Phase 1 onward.
"""

import logging

from celery_app import app

logger = logging.getLogger(__name__)


@app.task(bind=True, name="tasks.process.check_pending_backfill.check_pending_backfill")
def check_pending_backfill(self, batch_size: int = 50) -> dict:
    from tasks.process.backfill import sync_pending_backfill

    return sync_pending_backfill.apply(kwargs={"batch_size": batch_size}).get()
