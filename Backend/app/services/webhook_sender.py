import requests
import logging
import time
from typing import Dict, Any
from backend.app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_RETRIES = int(getattr(settings, "WEBHOOK_RETRIES", 3))
DEFAULT_BACKOFF = float(getattr(settings, "WEBHOOK_BACKOFF", 1.0))

def send_webhook(url: str, payload: Dict[str, Any], headers: Dict[str,str] = None, retries: int = DEFAULT_RETRIES) -> bool:
    headers = headers or {"Content-Type":"application/json"}
    attempt = 0
    while attempt <= retries:
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            if 200 <= r.status_code < 300:
                return True
            else:
                logger.warning("webhook non-2xx %s -> %s", r.status_code, r.text)
        except Exception as e:
            logger.exception("webhook attempt failed: %s", e)
        attempt += 1
        time.sleep(DEFAULT_BACKOFF * (2 ** (attempt-1)))
    return False

# Helper: register events to send asynchronously via Celery if you prefer
from backend.app.celery_app import celery_app

@celery_app.task(bind=True, max_retries=3)
def webhook_task(self, url: str, payload: Dict[str, Any], headers: Dict[str,str] = None):
    ok = send_webhook(url, payload, headers=headers, retries=0)
    if not ok:
        raise self.retry(countdown=60)
    return True


import requests, logging, time
from backend.app.celery_app import celery_app
from backend.app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_RETRIES = int(getattr(settings, "WEBHOOK_RETRIES", 3))
DEFAULT_BACKOFF = float(getattr(settings, "WEBHOOK_BACKOFF", 2.0))

def send_webhook_once(url: str, payload: dict, headers=None, timeout=10):
    headers = headers or {"Content-Type":"application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    return r.status_code, r.text

@celery_app.task(bind=True, max_retries=5, name="webhook.task")
def webhook_task(self, url: str, payload: dict, headers=None):
    try:
        code, text = send_webhook_once(url, payload, headers=headers)
        if 200 <= code < 300:
            return True
        else:
            raise Exception(f"non-2xx: {code} {text}")
    except Exception as e:
        try:
            delay = (2 ** self.request.retries) * DEFAULT_BACKOFF
            raise self.retry(countdown=delay, exc=e)
        except self.MaxRetriesExceededError:
            logger.exception("webhook failed permanently: %s", e)
            return False
