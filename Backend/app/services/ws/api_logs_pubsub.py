
# Backend/app/services/ws/api_logs_pubsub.py
import json
import asyncio
import logging
import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_URL = "redis://localhost:6379/7"   # separate channel for logs
CHANNEL = "admin_api_logs"

# Global redis client
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

async def publish_api_log(payload: dict):
    """
    Publish a log event (dict) to Redis pub/sub.
    Every worker process publishes here.
    """
    try:
        await redis_client.publish(CHANNEL, json.dumps(payload))
    except Exception as e:
        logger.error("Redis publish_api_log error: %s", e)


async def subscribe_and_forward(ws_manager):
    """
    Background worker that subscribes to Redis channel and forwards
    events to in-process WebSocket clients.
    Each backend process runs ONE subscriber.
    """
    sub = redis_client.pubsub()
    await sub.subscribe(CHANNEL)

    logger.info("Admin Log PubSub subscriber started.")

    async for msg in sub.listen():
        if msg["type"] != "message":
            continue
        try:
            payload = json.loads(msg["data"])
            await ws_manager.broadcast(payload)
        except Exception:
            logger.exception("Failed to forward pubsub message")
