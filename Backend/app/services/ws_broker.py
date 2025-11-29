"""
ws_broker: Redis Pub/Sub broker for real-time WebSocket fanout.

Architecture:
Celery (sync) → asyncio.run(ws_broker.publish(...))
FastAPI WS (async) → async for msg in ws_broker.subscribe(channel)

Used for:
- Bulk verification WS
- Verification stream WS
- Admin metrics WS
- Decision Maker enrichment WS
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis  # pip install redis>=4.3

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------
# SETTINGS
# --------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# global redis client (publish + create pubsubs)
_redis_client: Optional[aioredis.Redis] = None


def _get_client() -> aioredis.Redis:
    """Lazy init single Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            encoding="utf-8",
            health_check_interval=30,
        )
    return _redis_client


# --------------------------------------------------------------------
# Main Broker Class
# --------------------------------------------------------------------
class WSBroker:
    """
    - publish(channel, payload)
    - subscribe(channel) → async generator yielding messages
    """

    def __init__(self):
        self.client = _get_client()

    # --------------------------------------------------------------
    # Publish a JSON message
    # --------------------------------------------------------------
    async def publish(self, channel: str, payload: dict) -> int:
        """
        Publish a dict to Redis PubSub channel.
        Returns number of subscribers (Redis publish return value).
        """
        try:
            msg = json.dumps(payload, default=str)
            return int(await self.client.publish(channel, msg))
        except Exception as e:
            logger.exception(f"Redis publish failed ({channel}): {e}")
            return 0

    # --------------------------------------------------------------
    # Subscribe generator for WebSocket router
    # --------------------------------------------------------------
    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        """
        Subscribe to a channel and stream messages forever until cancelled.

        Usage:
            async for data in ws_broker.subscribe("bulk:123"):
                await ws.send_json(data)
        """
        pubsub = self.client.pubsub(ignore_subscribe_messages=True)

        try:
            await pubsub.subscribe(channel)
            logger.info(f"[ws_broker] Subscribed to channel: {channel}")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                raw = message.get("data")
                if raw is None:
                    continue

                try:
                    yield json.loads(raw)
                except Exception:
                    yield {"_raw": raw}

        except asyncio.CancelledError:
            logger.info(f"[ws_broker] Subscription cancelled for {channel}")
            raise

        except Exception as e:
            logger.exception(f"Subscriber crashed on {channel}: {e}")

        finally:
            try:
                await pubsub.unsubscribe(channel)
            except:
                pass

            try:
                await pubsub.close()
            except:
                pass

            logger.info(f"[ws_broker] Unsubscribed from: {channel}")

    # --------------------------------------------------------------
    # Explicit close (used only on shutdown)
    # --------------------------------------------------------------
    async def close(self):
        """Close global Redis connection."""
        global _redis_client
        try:
            if _redis_client:
                await _redis_client.close()
                _redis_client = None
        except Exception as e:
            logger.exception(f"ws_broker.close failed: {e}")


# --------------------------------------------------------------------
# GLOBAL SINGLETON
# --------------------------------------------------------------------
ws_broker = WSBroker()
