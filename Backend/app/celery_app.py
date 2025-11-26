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

REDIS_URL = getattr(settings, "CELERY_BROKER_URL", None) \
    or getattr(settings, "REDIS_URL", None) \
    or os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")

RESULT_BACKEND = getattr(settings, "CELERY_RESULT_BACKEND", None) or REDIS_URL


def make_celery_app(app_name: str = "email_verification_saas") -> Celery:
    celery = Celery(
        app_name,
        broker=REDIS_URL,
        backend=RESULT_BACKEND,
        include=[
            "backend.app.tasks.bulk_tasks",
            "backend.app.tasks.webhook_tasks",
            "backend.app.tasks.dlq_retry_task",
        ],
    )

    # ---------------------------------------------------------
    # CORE CONFIG
    # ---------------------------------------------------------
    celery.conf.update(
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_reject_on_worker_lost=True,
        worker_max_tasks_per_child=200,
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

    # ---------------------------------------------------------
    # QUEUES
    # ---------------------------------------------------------
    celery.conf.task_queues = (
        [
            Queue("default", Exchange("default"), routing_key="default"),
            Queue("bulk_jobs", Exchange("bulk_jobs"), routing_key="bulk_jobs"),
            Queue("webhooks", Exchange("webhooks"), routing_key="webhooks"),
            Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
        ]
    )

    # ---------------------------------------------------------
    # ROUTES
    # ---------------------------------------------------------
    celery.conf.task_routes = {
        "backend.app.tasks.bulk_tasks.process_bulk_job_task": {
            "queue": "bulk_jobs",
            "routing_key": "bulk_jobs",
        },
        "webhook.task": {
            "queue": "webhooks",
            "routing_key": "webhooks",
        },
        "dlq.retry.worker": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
    }

    # ---------------------------------------------------------
    # ⏰ CELERY BEAT SCHEDULE (DLQ auto retry every 5 min)
    # ---------------------------------------------------------
    celery.conf.beat_schedule = {
        "retry-dlq-every-5min": {
            "task": "dlq.retry.worker",
            "schedule": 300,  # 5 minutes
        }
    }

    # ---------------------------------------------------------
    # TIME LIMITS
    # ---------------------------------------------------------
    celery.conf.task_time_limit = int(
        getattr(settings, "CELERY_TASK_TIME_LIMIT", 300)
    )
    celery.conf.task_soft_time_limit = int(
        getattr(settings, "CELERY_TASK_SOFT_TIME_LIMIT", 240)
    )

    return celery


# Singleton instance
celery_app = make_celery_app()
# backend/app/celery_app.py
from celery import Celery
import time
import logging
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

app = Celery(
    "backend_tasks",
    broker="redis://localhost:6379/1",  # replace with settings.REDIS_URL or your broker
    backend="redis://localhost:6379/2",
)

# ----------------------
# Worker Prometheus metrics
# ----------------------
WORKER_TASK_TOTAL = Counter(
    "worker_tasks_total",
    "Worker tasks executed",
    ["task", "status"]  # status: started|success|failed
)

WORKER_TASK_LATENCY = Histogram(
    "worker_task_latency_seconds",
    "Latency of worker tasks",
    ["task"]
)

# Example: instrument tasks centrally using base task
class InstrumentedTask(app.Task):
    def __call__(self, *args, **kwargs):
        task_name = self.name or "unknown"
        WORKER_TASK_TOTAL.labels(task=task_name, status="started").inc()
        start = time.time()
        try:
            result = self.run(*args, **kwargs)
            WORKER_TASK_TOTAL.labels(task=task_name, status="success").inc()
            return result
        except Exception as exc:
            WORKER_TASK_TOTAL.labels(task=task_name, status="failed").inc()
            raise
        finally:
            WORKER_TASK_LATENCY.labels(task=task_name).observe(time.time() - start)

# Set default task base so all tasks inherit instrumentation
app.Task = InstrumentedTask
