# backend/app/services/ws_broker.py
"""
ws_broker: Production-grade Redis Pub/Sub broker for real-time fanout.

Architecture:
    Celery Worker  →  publish_sync()  → Redis (sync client)
    FastAPI WS     →  subscribe()    → Redis (async client)

Usage:
    from backend.app.services.ws_broker import ws_broker

    # From async code (FastAPI)
    await ws_broker.publish("bulk:JOBID", {"event": "progress", ...})

    # From sync code (Celery)
    ws_broker.publish_sync("bulk:JOBID", {"event": "progress", ...})

    # Subscribe (in FastAPI WebSocket router):
    async for msg in ws_broker.subscribe("bulk:JOBID"):
        await websocket.send_text(json.dumps(msg))
"""
from __future__ import annotations

import os
import json
import logging
import asyncio
from typing import Optional, AsyncIterator, Any, Dict

import redis.asyncio as aioredis      # async redis client (redis>=4.x)
import redis as redis_sync           # sync redis for Celery publish

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# SETTINGS
# -------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Singleton async client (used for subscribe & async publish)
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
    """
    Async publish/subscribe helper with a sync publish helper for Celery workers.

    - publish(channel, payload): async publish (FastAPI / async services)
    - publish_sync(channel, payload): sync publish for Celery (no event loop usage)
    - subscribe(channel): async generator yielding messages (FastAPI WS)
    - close(): async close of the async client
    """

    # -----------------------------
    # ASYNC PUBLISH (API, WS, etc.)
    # -----------------------------
    async def publish(self, channel: str, payload: Dict[str, Any]) -> int:
        """
        Async publish for FastAPI & async services.
        Returns number of clients that received the message (Redis PUBLISH return).
        """
        try:
            client = _get_async_client()
            message = json.dumps(payload, default=str)
            result = await client.publish(channel, message)
            return int(result)
        except Exception as e:
            logger.exception("ws_broker.publish failed: %s", e)
            return 0

    # -----------------------------
    # SYNC PUBLISH (CELERY WORKERS)
    # -----------------------------
    def publish_sync(self, channel: str, payload: Dict[str, Any]) -> int:
        """
        Sync publish for Celery tasks (NO asyncio.run needed).
        Creates a short-lived sync client per-call to avoid event-loop issues
        inside Celery worker processes.
        Returns number of clients that received the message (int).
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
    async def subscribe(self, channel: str) -> AsyncIterator[Dict[str, Any]]:
        """
        Async generator for Redis subscription.
        Yields JSON-decoded dicts (or {'_raw': ...} if decoding fails).

        Usage:
            async for event in ws_broker.subscribe("bulk:123"):
                await websocket.send_text(json.dumps(event))
        """
        client = _get_async_client()
        pubsub = client.pubsub(ignore_subscribe_messages=True)

        try:
            await pubsub.subscribe(channel)
            logger.info(f"[Redis-WS] Subscribed → {channel}")

            async for message in pubsub.listen():
                # message example: {'type': 'message', 'pattern': None, 'channel': 'bulk:123', 'data': '...'}
                if not message:
                    continue
                if message.get("type") != "message":
                    continue

                raw = message.get("data")
                if raw is None:
                    continue

                try:
                    yield json.loads(raw)
                except Exception:
                    # fallback with raw payload
                    yield {"_raw": raw}

        except asyncio.CancelledError:
            # allow cancellation to propagate
            raise

        except Exception as e:
            logger.exception("ws_broker.subscribe error (%s): %s", channel, e)

        finally:
            # Best-effort cleanup
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
    async def close(self) -> None:
        """
        Close the global async redis client (awaitable).
        """
        global _async_client
        try:
            if _async_client:
                await _async_client.close()
                _async_client = None
        except Exception:
            logger.exception("ws_broker.close failed")


# Module-level singleton
ws_broker = WSBroker()
