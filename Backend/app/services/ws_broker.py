
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
# backend/app/services/ws_broker.py
"""
Redis PubSub broker used for:
- Bulk verification WS streams
- User verification streams
- Admin metrics streams
- DM streams (optional)

Celery (sync) → publish()
FastAPI (async WS) → subscribe()

Designed for high throughput & multi-worker scaling.
"""

import os
import json
import asyncio
import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class RedisPubSubBroker:
    def __init__(self, url: str):
        self.url = url
        self._redis = aioredis.from_url(url, decode_responses=True)
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, data: dict):
        """
        Called by Celery worker using asyncio.run(ws_broker.publish(...))
        """
        try:
            msg = json.dumps(data)
            await self._redis.publish(channel, msg)
        except Exception as e:
            logger.error(f"Redis publish failed for {channel}: {e}")

    async def subscribe(self, channel: str) -> AsyncGenerator[dict, None]:
        """
        Called by FastAPI WS to forward messages to browser clients.
        """
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        yield json.loads(message["data"])
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Redis subscribe failed ({channel}): {e}")
            await asyncio.sleep(0.5)
            return


# Create shared instance
ws_broker = RedisPubSubBroker(REDIS_URL)

