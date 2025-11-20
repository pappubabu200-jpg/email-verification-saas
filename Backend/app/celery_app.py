from celery import Celery
import os
from backend.app.config import settings

broker = os.getenv("CELERY_BROKER_URL") or settings.CELERY_BROKER_URL or settings.REDIS_URL
celery_app = Celery("worker", broker=broker, backend=broker)
# In production you may want to disable task_always_eager and run real workers.
celery_app.conf.task_always_eager = False
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
