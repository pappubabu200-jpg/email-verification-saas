# backend/app/tasks/dlq_retry.py

import json
import time
import logging

from backend.app.celery_app import celery_app
from backend.app.tasks.webhook_tasks import webhook_task
from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository
from backend.app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BACKOFF = float(getattr(settings, "DLQ_RETRY_BACKOFF", 2.0))
MAX_BACKOFF_POWER = 6   # prevents crazy-large backoff delays


@celery_app.task(
    name="dlq.retry.worker",
    bind=True,
    max_retries=0,     # this worker itself does NOT retry
)
def dlq_retry_worker(self):
    """
    DLQ Retry Worker
    ----------------
    Runs every few minutes via Celery Beat.

    Workflow:
    1. Fetch all WebhookDLQ rows that are NOT processed
    2. For each:
         - Calculate exponential backoff based on attempts
         - Retry delivery by calling webhook_task.delay()
         - On success → mark processed
         - On failure → increase attempts counter
    """

    repo = WebhookDLQRepository()
    entries = repo.list(limit=200, offset=0, only_unprocessed=True)

    if not entries:
        logger.info("[DLQ] No pending entries.")
        return {"retried": 0}

    logger.info(f"[DLQ] Retrying {len(entries)} failed webhook events...")

    retried = 0

    for entry in entries:
        try:
            # -----------------------------------------
            # Parse payload & headers safely
            # -----------------------------------------
            try:
                payload = json.loads(entry.payload) if isinstance(entry.payload, str) else entry.payload
            except Exception:
                payload = entry.payload

            try:
                headers = json.loads(entry.headers) if entry.headers else None
            except Exception:
                headers = None

            # -----------------------------------------
            # Exponential Backoff BEFORE retry
            # -----------------------------------------
            power = min(entry.attempts, MAX_BACKOFF_POWER)
            delay_before = DEFAULT_BACKOFF * (2 ** power)
            time.sleep(delay_before)

            # -----------------------------------------
            # Delegate retry to original webhook task
            # -----------------------------------------
            async_result = webhook_task.delay(entry.url, payload, headers)

            # Task queued → mark processed in DLQ
            repo.mark_processed(entry.id)

            retried += 1
            logger.info(f"[DLQ] Re-queued webhook (id={entry.id}) url={entry.url}")

        except Exception as e:
            # Mark failed attempt
            repo.increment_attempts(entry.id, error=str(e))
            logger.error(f"[DLQ] Failed to retry entry id={entry.id}: {e}")

    return {"retried": retried}
