
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
# backend/app/services/ws_broker.py
"""
Aioredis-backed pubsub broker helper.

Usage:
  from backend.app.services.ws_broker import ws_broker
  await ws_broker.publish("channel", {"event":"x"})
  # In FastAPI WS handler subscribe manually to Redis using ws_broker.get_redis()
"""

import os
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis  # requires redis>=4.x

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class _WSBroker:
    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    def _ensure(self):
        if self._redis is None:
            self._redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    def get_redis(self) -> aioredis.Redis:
        """Return aioredis client (async)."""
        self._ensure()
        assert self._redis is not None
        return self._redis

    async def publish(self, channel: str, payload: Any) -> None:
        """Publish JSON payload to channel."""
        try:
            self._ensure()
            assert self._redis is not None
            msg = json.dumps(payload, default=str)
            await self._redis.publish(channel, msg)
        except Exception as e:
            logger.exception("ws_broker.publish failed: %s", e)

    async def close(self) -> None:
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None


# singleton
ws_broker = _WSBroker()


# backend/app/services/ws_broker.py
"""
ws_broker: lightweight aioredis-backed Pub/Sub helper for Redis.

Provides:
- ws_broker.publish(channel: str, payload: dict) -> publish message (async)
- ws_broker.subscribe(channel: str) -> async generator yielding dict messages
- ws_broker.close() -> close redis connection(s)

Notes:
- Uses `redis.asyncio` (pip install redis>=4.2.0)
- Messages are JSON-encoded strings on Redis channels.
- subscribe() returns an async generator — remember to `async for msg in subscribe(...)`.
"""

from __future__ import annotations

import os
import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis  # redis >=4.2
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Single global client for publishing; new pubsub instances created for each subscriber
_redis_client: Optional[aioredis.Redis] = None


def _get_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


class WSBroker:
    def __init__(self):
        self._client = _get_client()

    async def publish(self, channel: str, payload: dict) -> int:
        """
        Publish JSON payload to a Redis channel.
        Returns number of clients that received the message (Redis PUBLISH return).
        """
        try:
            body = json.dumps(payload, default=str)
            result = await self._client.publish(channel, body)
            return int(result)
        except Exception as e:
            logger.exception("ws_broker.publish failed: %s", e)
            return 0

    async def subscribe(self, channel: str, *, buffer: int = 100) -> AsyncIterator[dict]:
        """
        Subscribe to a channel and yield JSON-decoded messages as dicts.
        This returns an async generator. Example usage:
            async for msg in ws_broker.subscribe(f"bulk:{job_id}"):
                # msg is dict
        IMPORTANT: Caller should cancel/close the generator to free resources.
        """
        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        try:
            await pubsub.subscribe(channel)
            # pubsub.listen is an async iterator
            async for item in pubsub.listen():
                # item example: {'type': 'message', 'pattern': None, 'channel': 'bulk:123', 'data': '...'}
                try:
                    data = item.get("data")
                    if isinstance(data, str):
                        # decode JSON
                        try:
                            payload = json.loads(data)
                        except Exception:
                            # not JSON -> send raw
                            payload = {"_raw": data}
                    else:
                        payload = {"_raw": data}
                    yield payload
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error handling pubsub message", exc_info=True)
                    continue
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                logger.debug("Failed to unsubscribe from channel %s", channel)
            try:
                await pubsub.close()
            except Exception:
                pass

    async def close(self):
        global _redis_client
        try:
            if _redis_client:
                await _redis_client.close()
                _redis_client = None
        except Exception:
            logger.exception("ws_broker.close failed", exc_info=True)


# module-level instance
ws_broker = WSBroker()

