# backend/app/tasks/webhook_tasks.py
import requests
import logging
from backend.app.celery_app import celery_app
from backend.app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_BACKOFF = float(getattr(settings, "WEBHOOK_BACKOFF", 2.0))


def send_webhook_once(url: str, payload: dict, headers=None, timeout=10):
    """
    Single attempt — no retry here.
    Used inside Celery task which handles retries itself.
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
    Production webhook delivery:
    - Celery retry backoff
    - Logs failures
    - 5 retry attempts
    - Exponential backoff
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
            logger.error(f"[WEBHOOK] PERMANENT FAILURE url={url} err={e}")
            return False
