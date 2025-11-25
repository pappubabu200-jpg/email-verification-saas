# backend/app/services/webhook_sender.py
import logging
from backend.app.tasks.webhook_tasks import webhook_task

logger = logging.getLogger(__name__)

def enqueue_webhook(url: str, payload: dict, headers=None) -> bool:
    """
    Safe interface for your app code to queue webhooks.
    Used by bulk processor + event triggers.
    """
    try:
        webhook_task.delay(url, payload, headers)
        return True
    except Exception as e:
        logger.exception(f"Failed to enqueue webhook: {e}")
        return False
