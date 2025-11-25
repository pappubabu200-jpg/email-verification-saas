# backend/app/tasks/dlq_retry.py
import logging
import time
from typing import Any, Dict
from backend.app.celery_app import celery_app
from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository
from backend.app.tasks.webhook_tasks import send_webhook_once  # lightweight synchronous helper
from backend.app.config import settings

logger = logging.getLogger(__name__)

# Retry policy for reprocessing DLQ entries: exponential backoff per attempt
RETRY_BACKOFF_BASE = float(getattr(settings, "DLQ_RETRY_BASE", 2.0))
RETRY_BATCH_SIZE = int(getattr(settings, "DLQ_RETRY_BATCH", 50))


@celery_app.task(bind=True, name="dlq.retry.worker", max_retries=0)
def retry_webhook_dlq_batch(self, batch_size: int = RETRY_BATCH_SIZE) -> int:
    """
    Fetch a batch of unprocessed DLQ entries and attempt to resend them.
    If success => mark processed, else increment attempts + update error.
    This task is designed to be scheduled (beat) or called manually.
    Returns number of processed entries attempted.
    """
    repo = WebhookDLQRepository()
    entries = repo.list(limit=batch_size, only_unprocessed=True)
    processed_count = 0

    for entry in entries:
        try:
            payload = entry.payload or {}
            headers = entry.headers or {"Content-Type": "application/json"}
            # attempt delivery (single try). We don't want to block the worker for a huge time.
            code, text = send_webhook_once(entry.url, payload, headers=headers, timeout=10)
            if 200 <= code < 300:
                repo.mark_processed(entry.id)
                logger.info(f"[DLQ] Re-delivered id={entry.id} url={entry.url} code={code}")
            else:
                # update attempts + error
                repo.increment_attempts(entry.id, error=f"non-2xx {code}: {text}")
                logger.warning(f"[DLQ] Re-delivery failed id={entry.id} url={entry.url} code={code}")
            processed_count += 1
            # small sleep to avoid thundering on remote endpoints
            time.sleep(0.05)
        except Exception as e:
            try:
                repo.increment_attempts(entry.id, error=str(e))
            except Exception:
                logger.exception("Failed to update DLQ attempts")
            logger.exception(f"[DLQ] Exception while re-delivering id={entry.id}: {e}")
            processed_count += 1
            time.sleep(0.05)

    return processed_count
