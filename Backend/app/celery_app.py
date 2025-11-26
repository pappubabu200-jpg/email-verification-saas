# backend/app/celery_app.py
"""
Celery application factory + shared singleton instance
with Prometheus worker instrumentation.
"""

from __future__ import annotations

import os
import time
import logging
from celery import Celery
from kombu import Exchange, Queue
from prometheus_client import Counter, Histogram

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# REDIS BROKER & BACKEND
# ---------------------------------------------------------
REDIS_URL = getattr(settings, "CELERY_BROKER_URL", None) \
    or getattr(settings, "REDIS_URL", None) \
    or os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")

RESULT_BACKEND = getattr(settings, "CELERY_RESULT_BACKEND", None) or REDIS_URL


# ---------------------------------------------------------
# PROMETHEUS METRICS
# ---------------------------------------------------------
WORKER_TASK_TOTAL = Counter(
    "worker_tasks_total",
    "Worker tasks executed",
    ["task", "status"]
)

WORKER_TASK_LATENCY = Histogram(
    "worker_task_latency_seconds",
    "Latency of worker tasks",
    ["task"]
)


# ---------------------------------------------------------
# Instrumented Task Wrapper (global)
# ---------------------------------------------------------
class InstrumentedTask(Celery.Task):
    """
    Wraps all Celery tasks with:
    - start counter
    - success counter
    - failure counter
    - latency histogram
    """
    def __call__(self, *args, **kwargs):
        task_name = self.name or "unknown"

        WORKER_TASK_TOTAL.labels(task=task_name, status="started").inc()
        start = time.time()

        try:
            result = self.run(*args, **kwargs)
            WORKER_TASK_TOTAL.labels(task=task_name, status="success").inc()
            return result

        except Exception:
            WORKER_TASK_TOTAL.labels(task=task_name, status="failed").inc()
            raise

        finally:
            WORKER_TASK_LATENCY.labels(task=task_name).observe(time.time() - start)


# ---------------------------------------------------------
# Celery App Factory
# ---------------------------------------------------------
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

    # Set global InstrumentedTask wrapper
    celery.Task = InstrumentedTask

    # -----------------------------
    # CORE CONFIG
    # -----------------------------
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

    # -----------------------------
    # QUEUES
    # -----------------------------
    celery.conf.task_queues = (
        [
            Queue("default", Exchange("default"), routing_key="default"),
            Queue("bulk_jobs", Exchange("bulk_jobs"), routing_key="bulk_jobs"),
            Queue("webhooks", Exchange("webhooks"), routing_key="webhooks"),
            Queue("low_priority", Exchange("low_priority"), routing_key="low_priority"),
        ]
    )

    # -----------------------------
    # ROUTES
    # -----------------------------
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

    # -----------------------------
    # CELERY BEAT (DLQ auto retry)
    # -----------------------------
    celery.conf.beat_schedule = {
        "retry-dlq-every-5min": {
            "task": "dlq.retry.worker",
            "schedule": 300,
        }
    }

    # -----------------------------
    # TIME LIMITS
    # -----------------------------
    celery.conf.task_time_limit = int(
        getattr(settings, "CELERY_TASK_TIME_LIMIT", 300)
    )
    celery.conf.task_soft_time_limit = int(
        getattr(settings, "CELERY_TASK_SOFT_TIME_LIMIT", 240)
    )

    return celery


# ---------------------------------------------------------
# Singleton Instance
# ---------------------------------------------------------
celery_app = make_celery_app()
