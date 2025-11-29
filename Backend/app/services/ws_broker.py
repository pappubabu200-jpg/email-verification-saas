"""
ws_broker: Production-grade Redis Pub/Sub broker for real-time fanout.

Architecture:
    Celery Worker  →  publish_sync()  → Redis
    FastAPI WS     →  subscribe()    → Redis → WebSocket

This file replaces ALL other ws_broker* files in the repo.
"""

from __future__ import annotations

import os
import json
import logging
import asyncio
from typing import Optional, AsyncIterator, Any

# Async Redis for WS subscribe & async publish
import redis.asyncio as aioredis
# Sync Redis for Celery publish (no event-loop issues)
import redis as redis_sync

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# SETTINGS
# -------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Singleton async client
_async_client: Optional[aioredis.Redis] = None


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _get_async_client() -> aioredis.Redis:
    """
    Create or return the global async Redis client.
    Used by subscribe() and async publish().
    """
    global _async_client
    if _async_client is None:
        _async_client = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            encoding="utf-8",
            health_check_interval=30,
        )
    return _async_client


# -------------------------------------------------------------------
# Broker class
# -------------------------------------------------------------------
class WSBroker:

    # -----------------------------
    # ASYNC PUBLISH (API, WS, etc.)
    # -----------------------------
    async def publish(self, channel: str, payload: dict) -> int:
        """
        Async publish for FastAPI & async services.
        """
        try:
            client = _get_async_client()
            message = json.dumps(payload, default=str)
            return int(await client.publish(channel, message))
        except Exception as e:
            logger.exception("ws_broker.publish failed: %s", e)
            return 0

    # -----------------------------
    # SYNC PUBLISH (CELERY WORKERS)
    # -----------------------------
    def publish_sync(self, channel: str, payload: dict) -> int:
        """
        Sync publish for Celery tasks (NO asyncio.run needed).
        This is extremely important because Celery runs in a
        separate processes without async event loops.
        """
        try:
            r = redis_sync.from_url(REDIS_URL, decode_responses=True)
            msg = json.dumps(payload, default=str)
            return int(r.publish(channel, msg))
        except Exception as e:
            logger.exception("ws_broker.publish_sync failed: %s", e)
            return 0

    # -----------------------------
    # SUBSCRIBE (FastAPI WebSockets)
    # -----------------------------
    async def subscribe(self, channel: str) -> AsyncIterator[dict]:
        """
        Async generator for Redis subscription.
        Used inside FastAPI WebSocket routers.

        Example:
            async for event in ws_broker.subscribe("bulk:123"):
                await websocket.send_text(json.dumps(event))
        """
        client = _get_async_client()
        pubsub = client.pubsub(ignore_subscribe_messages=True)

        try:
            await pubsub.subscribe(channel)
            logger.info(f"[Redis-WS] Subscribed → {channel}")

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
            raise

        except Exception as e:
            logger.exception("ws_broker.subscribe error (%s): %s", channel, e)

        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                await pubsub.close()
            except Exception:
                pass

            logger.info(f"[Redis-WS] Unsubscribed ← {channel}")

    # -----------------------------
    # CLEANUP
    # -----------------------------
    async def close(self):
        global _async_client
        try:
            if _async_client:
                await _async_client.close()
                _async_client = None
        except Exception:
            logger.exception("ws_broker.close failed")
