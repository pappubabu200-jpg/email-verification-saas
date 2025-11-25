# backend/app/celery_app.py

from celery import Celery
from kombu import Exchange, Queue
import os
import logging

from backend.app.config import settings

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# CELERY CONNECTION SETTINGS
# -----------------------------------------------------------------------------
REDIS_URL = getattr(settings, "REDIS_URL", os.getenv("REDIS_URL", "redis://redis:6379/0"))
CELERY_BROKER_URL = getattr(settings, "CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = getattr(settings, "CELERY_RESULT_BACKEND", REDIS_URL)


# -----------------------------------------------------------------------------
# FACTORY: CREATE CELERY APP
# -----------------------------------------------------------------------------
def make_celery_app(app_name: str = "email_verification_saas") -> Celery:
    celery = Celery(
        app_name,
        broker=CELERY_BROKER_URL,
        backend=CELERY_RESULT_BACKEND,
        include=[
            "backend.app.tasks.bulk_tasks",
        ],
    )

    # -----------------------------------------------------------------------------
    # CORE CONFIG
    # -----------------------------------------------------------------------------
    celery.conf.update(
        task_acks_late=True,               # Only acknowledge when done
        worker_prefetch_multiplier=1,      # Prevents task starvation
        task_reject_on_worker_lost=True,   # Important for high reliability
        worker_max_tasks_per_child=100,    # Prevent slow memory leaks
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone=getattr(settings, "TIMEZONE", "UTC"),
        enable_utc=True,
        broker_pool_limit=10,
        broker_heartbeat=30,
        result_expires=3600,               # 1 hour
    )

    # -----------------------------------------------------------------------------
    # QUEUES
    # -----------------------------------------------------------------------------
    celery.conf.task_queues = [
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("bulk_jobs", Exchange("bulk_jobs"), routing_key="bulk_jobs"),
    ]

    # -----------------------------------------------------------------------------
    # ROUTES
    # -----------------------------------------------------------------------------
    celery.conf.task_routes = {
        "backend.app.tasks.bulk_tasks.process_bulk_job_task": {
            "queue": "bulk_jobs",
            "routing_key": "bulk_jobs",
        },
    }

    return celery


# -----------------------------------------------------------------------------
# GLOBAL CELERY INSTANCE
# -----------------------------------------------------------------------------
celery_app = make_celery_app()
