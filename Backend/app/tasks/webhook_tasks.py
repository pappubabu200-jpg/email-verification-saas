# backend/app/tasks/webhook_tasks.py
"""
Webhook delivery worker with:
- Exponential backoff
- Random jitter
- Timeout safety
- 5 retry attempts
- DLQ (dead-letter queue) optional
"""

from __future__ import annotations
import json
import logging
import random
import requests
from celery import shared_task

logger = logging.getLogger(__name__)

TIMEOUT = 6  # seconds
MAX_RETRIES = 5


@shared_task(
    bind=True,
    name="backend.app.tasks.webhook_tasks.send_webhook",
    autoretry_for=(Exception,),
    retry_backoff=True,        # exponential
    retry_backoff_max=60,      # 1 min
    retry_jitter=True,         # add randomness
    retry_kwargs={"max_retries": MAX_RETRIES},
)
def send_webhook(self, url: str, payload: dict):
    """
    POST JSON webhook with retries.
    """
    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=TIMEOUT,
            headers={"Content-Type": "application/json"},
        )

        # Retry on non-200
        if resp.status_code >= 400:
            logger.warning(
                f"Webhook failed ({resp.status_code}) -> retrying URL={url}"
            )
            raise Exception(f"webhook_http_error:{resp.status_code}")

        logger.info(f"Webhook delivered → {url}")
        return {"ok": True, "status": resp.status_code}

    except Exception as e:
        logger.exception(f"Webhook send error: {e}")
        raise  # triggers Celery autoretry
