# backend/app/services/ws_broker.py
"""
ws_broker: Aioredis Pub/Sub helper for real-time WebSocket fanout.

Used by:
- Bulk verification WS stream
- User verification WS stream
- Admin metrics
- Decision Maker enrichment stream

Architecture:
Celery (sync) → asyncio.run(ws_broker.publish())
FastAPI WS (async) → async for message in ws_broker.subscribe()
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis  # redis >= 4.2 required

logger = logging.getLogger(__name__)

# ------------------------------
# SETTINGS
# ------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Global Redis connection reused for publish & for creating pubsub channels
_redis_client: Optional[aioredis.Redis] = None


# ------------------------------
# Internal helper — single redis client
# ------------------------------
def _get_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            encoding="utf-8"
        )
    return _redis_client


# ------------------------------
# Broker class
# ------------------------------
class WSBroker:
    """
    - publish(): used by Celery tasks or API
    - subscribe(): used by WS router to forward redis messages to WebSocket

    Publish = fast, async safe.
    Subscribe = async generator yielding dict messages.
    """
    def __init__(self):
        self.client = _get_client()

    # --------------------------
    # Publish JSON message
    # --------------------------
    async def publish(self, channel: str, payload: dict) -> int:
        """
        Publish a dict to Redis PubSub channel.
        Must be JSON serializable.
        Returns number of clients that received message.
        """
        try:
            msg = json.dumps(payload, default=str)
            result = await self.client.publish(channel, msg)
            return int(result)
        except Exception as e:
            logger.exception(f"ws_broker.publish failed for channel={channel}: {e}")
            return 0

    # --------------------------
    # Subscribe → async generator
    # --------------------------
    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        """
        Yields messages forever until cancelled.

        Usage:
            async for msg in ws_broker.subscribe("bulk:123"):
                await websocket.send_text(json.dumps(msg))
        """
        pubsub = self.client.pubsub(ignore_subscribe_messages=True)

        try:
            await pubsub.subscribe(channel)
            logger.info(f"[Redis-WS] Subscribed to channel: {channel}")

            async for event in pubsub.listen():
                if event["type"] != "message":
                    continue

                raw = event.get("data")
                if raw is None:
                    continue

                try:
                    decoded = json.loads(raw)
                except Exception:
                    decoded = {"_raw": raw}

                yield decoded

        except asyncio.CancelledError:
            raise

        except Exception as e:
            logger.exception(f"ws_broker.subscribe crashed ({channel}): {e}")

        finally:
            # Clean unsubscribe
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass

            try:
                await pubsub.close()
            except Exception:
                pass

            logger.info(f"[Redis-WS] Unsubscribed from: {channel}")

    # --------------------------
    # Close global Redis connection
    # --------------------------
    async def close(self):
        global _redis_client
        try:
            if _redis_client:
                await _redis_client.close()
                _redis_client = None
        except Exception:
            logger.exception("ws_broker.close failed")


# GLOBAL SINGLETON
ws_broker = WSBroker()
