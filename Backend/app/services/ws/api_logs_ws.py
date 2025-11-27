# Backend/app/services/ws/api_logs_ws.py
import json
import asyncio
from typing import Set, Dict
from fastapi import WebSocket

class APILogsWSManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        # accept then add
        await ws.accept()
        async with self.lock:
            self.active.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, payload: Dict):
        """
        payload: arbitrary dict describing the API log event
        """
        text = json.dumps(payload, default=str)
        async with self.lock:
            dead = []
            for ws in set(self.active):
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.active.discard(ws)

# singleton instance
api_logs_ws = APILogsWSManager()

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
