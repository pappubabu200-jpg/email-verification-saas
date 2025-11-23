
# backend/app/services/webhook_dispatcher.py
import logging
import json
import requests
from backend.app.celery_app import celery_app

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 4

@celery_app.task(bind=True, max_retries=DEFAULT_RETRIES)
def send_webhook_async(self, url: str, payload: dict):
    """
    Reliable webhook sender for job completion, billing events, etc.
    Retries with exponential backoff.
    """
    try:
        r = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        if 200 <= r.status_code < 300:
            return True
        else:
            logger.warning("Webhook returned %s: %s", r.status_code, r.text)
            raise Exception("non_200_webhook")
    except Exception as e:
        logger.exception("Webhook failed: %s", e)
        raise self.retry(countdown=2 ** self.request.retries)
