
# backend/app/services/ws_broker.py
import json
import logging
import asyncio
import aioredis
from typing import Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"

class RedisWebSocketBroker:
    def __init__(self):
        self.redis = None
        self.pub = None
        self.loop = asyncio.get_event_loop()

    async def connect(self):
        if self.redis is None:
            self.redis = await aioredis.from_url(
                REDIS_URL, decode_responses=True
            )
            self.pub = self.redis.pubsub()

    async def publish(self, channel: str, message: dict):
        """ Called by Celery worker or API directly """
        await self.connect()
        data = json.dumps(message)
        await self.redis.publish(channel, data)

    async def subscribe(self, channel: str, handler: Callable[[dict], Coroutine]):
        """ FastAPI WebSocket – subscribes & pushes messages """
        await self.connect()

        sub = self.redis.pubsub()
        await sub.subscribe(channel)
        logger.info(f"WS subscribed to Redis channel: {channel}")

        async for event in sub.listen():
            if event["type"] == "message":
                payload = json.loads(event["data"])
                await handler(payload)


ws_broker = RedisWebSocketBroker()
