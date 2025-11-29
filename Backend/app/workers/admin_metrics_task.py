# backend/app/workers/admin_metrics_task.py
from backend.app.celery_app import celery_app
from backend.app.services.admin_metrics_publisher import publish_admin_metrics_sync
from backend.app.services.analytics_service import get_admin_metrics_snapshot

@celery_app.task(name="admin.send_metrics")
def admin_metrics_job():
    """
    Periodic task (every 5s).
    Push latest admin stats to Redis → WS.
    """
    metrics = get_admin_metrics_snapshot()  # {credits, verifications, deliverability, events}
    publish_admin_metrics_sync(metrics)
    return {"pushed": True}
