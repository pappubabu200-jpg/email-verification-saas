# backend/app/tasks/webhook_tasks.py

import requests
import logging
from backend.app.celery_app import celery_app
from backend.app.config import settings
from backend.app.repositories.webhook_dlq_repository import WebhookDLQRepository

logger = logging.getLogger(__name__)

DEFAULT_BACKOFF = float(getattr(settings, "WEBHOOK_BACKOFF", 2.0))


def send_webhook_once(url: str, payload: dict, headers=None, timeout=10):
    """
    Single attempt — no retry inside this function.
    Celery handles the retries.
    """
    headers = headers or {"Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    return r.status_code, r.text


@celery_app.task(
    bind=True,
    max_retries=5,
    name="webhook.task",
)
def webhook_task(self, url: str, payload: dict, headers=None):
    """
    Production webhook delivery task:

    ✔ Exponential backoff retry  
    ✔ Logs every attempt  
    ✔ Stores failed webhooks into DLQ after max retries  
    ✔ Highly reliable for bulk verification webhooks  
    """
    try:
        code, text = send_webhook_once(url, payload, headers=headers)

        if 200 <= code < 300:
            logger.info(f"[WEBHOOK] Delivered to {url} -> {code}")
            return True

        raise Exception(f"non-2xx response: {code} {text}")

    except Exception as e:
        # exponential backoff = (BACKOFF * 2^retry)
        delay = DEFAULT_BACKOFF * (2 ** self.request.retries)
        logger.warning(f"[WEBHOOK] Retry in {delay:.1f}s error={e}")

        try:
            raise self.retry(countdown=delay, exc=e)

        except self.MaxRetriesExceededError:
            # ============================================
            # 🔥 PERMANENT FAILURE — SAVE TO DLQ (Critical)
            # ============================================
            try:
                repo = WebhookDLQRepository()
                repo.save(
                    url=url,
                    payload=payload,
                    headers=headers,
                    error=str(e),
                    attempts=self.request.retries,
                )
                logger.error(f"[WEBHOOK] PERMANENT FAILURE saved to DLQ url={url} err={e}")
            except Exception as db_err:
                logger.exception(f"[WEBHOOK][DLQ] Failed to store DLQ record: {db_err}")

            return False
