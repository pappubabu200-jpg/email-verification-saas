# backend/app/celery_app.py
"""
Celery application factory + shared instance.

Usage:
    from backend.app.celery_app import celery_app
    celery_app.send_task(...)  # or import tasks directly
"""
from __future__ import annotations

import os
import logging
from celery import Celery
from kombu import Exchange, Queue

from backend.app.config import settings

logger = logging.getLogger(__name__)

REDIS_URL = getattr(settings, "CELERY_BROKER_URL", None) or getattr(settings, "REDIS_URL", None) or os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = getattr(settings, "CELERY_RESULT_BACKEND", None) or REDIS_URL

def make_celery_app(app_name: str = "email_verification_saas") -> Celery:
    celery = Celery(
        app_name,
        broker=REDIS_URL,
        backend=RESULT_BACKEND,
        include=[
            "backend.app.tasks.bulk_tasks",
            # add other task modules here if needed
        ],
    )

    # Recommended defaults for production - tune per workload
    celery.conf.update(
        task_acks_late=True,               # ack after task executed
        worker_prefetch_multiplier=1,      # fair work distribution
        task_reject_on_worker_lost=True,
        worker_max_tasks_per_child=200,    # recycle processes to avoid leaks
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone=getattr(settings, "TIMEZONE", "UTC"),
        enable_utc=True,
        broker_pool_limit=10,
        broker_heartbeat=30,
        result_expires=3600,
        task_default_queue="default",
        task_default_exchange="default",
        task_default_routing_key="default",
    )

    # Queues
    celery.conf.task_queues = (
        [
            Queue("default", Exchange("default"), routing_key="default"),
            Queue("bulk_jobs", Exchange("bulk_jobs"), routing_key="bulk_jobs"),
            Queue("webhooks", Exchange("webhooks"), routing_key="webhooks"),
            Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
        ]
    )

    # Routes - direct heavy jobs to bulk_jobs
    celery.conf.task_routes = {
        "backend.app.tasks.bulk_tasks.process_bulk_job_task": {"queue": "bulk_jobs", "routing_key": "bulk_jobs"},
        # add other routing rules here
    }

    # Soft and hard time limits can prevent stuck tasks (seconds)
    celery.conf.task_time_limit = int(getattr(settings, "CELERY_TASK_TIME_LIMIT", 300))    # hard limit
    celery.conf.task_soft_time_limit = int(getattr(settings, "CELERY_TASK_SOFT_TIME_LIMIT", 240))

    return celery

# singleton instance used by workers / app
celery_app = make_celery_app()
