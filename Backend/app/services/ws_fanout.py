# backend/app/services/ws_fanout.py
"""
High-performance fan-out WebSocket broadcaster.

1 Redis subscription → many WebSocket clients.
Clients register for specific channels:
    user:{id}:verification
    bulk:{jobId}
    admin:metrics

Redis → Fanout Hub → Connected WS Clients
"""

import asyncio
import json
import logging
from typing import Dict, Set, Callable

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = "redis://localhost:6379/0"

class FanoutHub:
    def __init__(self):
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.pubsub = self.redis.pubsub()

        # channel → set(WebSocket)
        self.subscribers: Dict[str, Set] = {}

        self._started = False

    async def start(self):
        """Start Redis listener once."""
        if self._started:
            return

        self._started = True
        asyncio.create_task(self._listener_loop())
        logger.info("FanoutHub Redis listener started.")

    async def subscribe_ws(self, channel: str, websocket):
        """Register WebSocket for a channel."""
        if channel not in self.subscribers:
            self.subscribers[channel] = set()
            # subscribe this channel in Redis (only once)
            await self.pubsub.subscribe(channel)

        self.subscribers[channel].add(websocket)
        logger.info(f"WS subscribed: {channel}, total={len(self.subscribers[channel])}")

    async def unsubscribe_ws(self, channel: str, websocket):
        """Remove WebSocket from channel."""
        if channel in self.subscribers:
            self.subscribers[channel].discard(websocket)
            if not self.subscribers[channel]:
                # empty → unsubscribe from Redis
                await self.pubsub.unsubscribe(channel)
                del self.subscribers[channel]
                logger.info(f"Unsubscribed Redis channel: {channel}")

    async def _listener_loop(self):
        """Background task: listens to Redis messages and fans out to WS clients."""
        logger.info("FanoutHub listener loop running...")

        while True:
            try:
                msg = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg:
                    channel = msg.get("channel")
                    data = msg.get("data")

                    # Ensure JSON
                    try:
                        payload = json.loads(data)
                    except Exception:
                        payload = data

                    # Broadcast
                    await self._broadcast(channel, payload)

            except Exception as e:
                logger.error("Fanout listener error: %s", e)
                await asyncio.sleep(1)

    async def _broadcast(self, channel: str, payload):
        """Send payload to all connected WebSocket clients for that channel."""
        if channel not in self.subscribers:
            return

        remove_list = []
        for ws in list(self.subscribers[channel]):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                remove_list.append(ws)

        # Cleanup closed WS
        for ws in remove_list:
            await self.unsubscribe_ws(channel, ws)


# Singleton fanout hub
ws_fanout = FanoutHub()
