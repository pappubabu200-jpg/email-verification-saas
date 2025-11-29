# backend/app/services/admin_metrics_publisher.py
import asyncio
from backend.app.services.ws_broker import ws_broker

ADMIN_CHANNEL = "admin:metrics"


async def publish_admin_metrics(payload: dict):
    """
    Publish admin analytics metrics to Redis fanout.
    """
    await ws_broker.publish(ADMIN_CHANNEL, payload)


def publish_admin_metrics_sync(payload: dict):
    """
    Sync wrapper for Celery or sync code.
    """
    try:
        asyncio.run(ws_broker.publish(ADMIN_CHANNEL, payload))
    except RuntimeError:
        # In case event loop already running (Celery safety)
        loop = asyncio.get_event_loop()
        loop.create_task(ws_broker.publish(ADMIN_CHANNEL, payload))
