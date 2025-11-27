# backend/app/services/dm_ws_manager.py
"""
Decision Maker WebSocket Manager (FINAL)
-----------------------------------------
Manages live sockets for:
 - dm_detail_ready
 - enrich_started
 - enrich_progress
 - enrich_completed
 - enrich_failed

Supports:
 - Rooms based on DM ID or Email
 - Broadcast to all subscribers
 - Safe usage from Celery workers (asyncio.run)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class DMWebSocketManager:
    def __init__(self):
        # room_id (email or id) → set(WebSocket)
        self.rooms: Dict[str, Set[WebSocket]] = {}
        # global lock helps concurrency
        self.lock = asyncio.Lock()

    # ------------------------------------------------------
    # Connection Management
    # ------------------------------------------------------
    async def connect(self, dm_id: str, websocket: WebSocket):
        """
        dm_id is email or decision-maker ID
        """
        await websocket.accept()
        async with self.lock:
            if dm_id not in self.rooms:
                self.rooms[dm_id] = set()
            self.rooms[dm_id].add(websocket)

        logger.info(f"[DM-WS] Client joined room {dm_id}. Now: {len(self.rooms[dm_id])}")

    async def disconnect(self, dm_id: str, websocket: WebSocket):
        async with self.lock:
            if dm_id in self.rooms and websocket in self.rooms[dm_id]:
                self.rooms[dm_id].remove(websocket)
                if len(self.rooms[dm_id]) == 0:
                    del self.rooms[dm_id]

        logger.info(f"[DM-WS] Client left room {dm_id}")

    # ------------------------------------------------------
    # Broadcast Helpers
    # ------------------------------------------------------
    async def broadcast(self, dm_id: str, payload: dict):
        """
        Broadcast message to all clients subscribed to this DM.
        """
        async with self.lock:
            sockets = list(self.rooms.get(dm_id, []))

        if not sockets:
            return

        msg = None
        try:
            import json
            msg = json.dumps(payload)
        except Exception:
            logger.error("Failed to serialize WS payload")

        for ws in sockets:
            try:
                await ws.send_text(msg)
            except WebSocketDisconnect:
                await self.disconnect(dm_id, ws)
            except Exception:
                logger.exception("WS send error; dropping client")
                await self.disconnect(dm_id, ws)

    # ------------------------------------------------------
    # Safe sync-style push (for worker usage)
    # ------------------------------------------------------
    def push(self, dm_id: str, payload: dict):
        """
        Can be called from ANY thread (Celery worker safe).
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            asyncio.create_task(self.broadcast(dm_id, payload))
        else:
            asyncio.run(self.broadcast(dm_id, payload))

    # Synchronous fallbacks (if needed)
    def push_sync(self, dm_id: str, payload: dict):
        asyncio.run(self.broadcast(dm_id, payload))


# Create manager instance
dm_ws_manager = DMWebSocketManager()
