# backend/app/workers/scheduler.py
from datetime import time
from celery.schedules import crontab
from backend.app.celery_app import celery_app
from backend.app.services.api_key_service import reset_all_api_keys_usage
import logging

logger = logging.getLogger(__name__)

# Schedule: run at 00:01 UTC every day (a minute after midnight)
@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # daily reset at 00:01 UTC
    sender.add_periodic_task(
        crontab(minute=1, hour=0),
        reset_daily.s(),
        name="reset_api_key_usage_daily"
    )

@celery_app.task
def reset_daily():
    logger.info("Running daily API key usage reset")
    reset_all_api_keys_usage()
    logger.info("Completed daily API key usage reset")
