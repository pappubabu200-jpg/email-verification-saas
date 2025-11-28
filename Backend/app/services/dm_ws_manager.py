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

# backend/app/services/dm_ws_manager.py
"""
Simple async WebSocket manager for Decision Maker events.

- Keeps track of connections keyed by job_id and dm_id.
- Provides async broadcast helpers for workers/services to call.
- Provides light sync fallback methods (broadcast_dm_sync / broadcast_job_sync)
  that will attempt to send messages synchronously (best-effort).
"""

import asyncio
import json
import logging
from typing import Dict, Set, Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Maps: job_id -> set(WebSocket)
_job_connections: Dict[str, Set[WebSocket]] = {}

# Maps: dm_id -> set(WebSocket]
_dm_connections: Dict[str, Set[WebSocket]] = {}

# Optionally map user_id -> set(WebSocket] (for user-specific streams)
_user_connections: Dict[str, Set[WebSocket]] = {}


# -------------------------
# Connection management
# -------------------------
async def connect_job(ws: WebSocket, job_id: str):
    """
    Accept a websocket after handshake and register it for a job_id channel.
    """
    await ws.accept()
    conns = _job_connections.setdefault(job_id, set())
    conns.add(ws)
    logger.debug("WS connected to job %s (total=%d)", job_id, len(conns))


async def disconnect_job(ws: WebSocket, job_id: str):
    conns = _job_connections.get(job_id)
    if not conns:
        return
    conns.discard(ws)
    if len(conns) == 0:
        _job_connections.pop(job_id, None)
    logger.debug("WS disconnected from job %s (remaining=%d)", job_id, len(conns or []))


async def connect_dm(ws: WebSocket, dm_id: str):
    await ws.accept()
    conns = _dm_connections.setdefault(dm_id, set())
    conns.add(ws)
    logger.debug("WS connected to dm %s (total=%d)", dm_id, len(conns))


async def disconnect_dm(ws: WebSocket, dm_id: str):
    conns = _dm_connections.get(dm_id)
    if not conns:
        return
    conns.discard(ws)
    if len(conns) == 0:
        _dm_connections.pop(dm_id, None)
    logger.debug("WS disconnected from dm %s (remaining=%d)", dm_id, len(conns or []))


# -------------------------
# Broadcasting helpers
# -------------------------
async def _safe_send(ws: WebSocket, payload: Any):
    try:
        if isinstance(payload, (dict, list)):
            await ws.send_text(json.dumps(payload))
        else:
            await ws.send_text(str(payload))
    except Exception as e:
        logger.debug("Failed to send ws message: %s", e)
        # ignore; connection cleanup happens on disconnect


async def broadcast_job(job_id: str, payload: Any):
    """
    Send payload to all clients listening to a job_id (async).
    """
    conns = list(_job_connections.get(job_id, set()))
    if not conns:
        return
    coros = [_safe_send(ws, payload) for ws in conns]
    await asyncio.gather(*coros, return_exceptions=True)


async def broadcast_dm(dm_id: str, payload: Any):
    """
    Send payload to all clients listening to a decision-maker (dm_id).
    """
    conns = list(_dm_connections.get(dm_id, set()))
    if not conns:
        return
    coros = [_safe_send(ws, payload) for ws in conns]
    await asyncio.gather(*coros, return_exceptions=True)


# -------------------------
# Sync fallbacks (best-effort)
# -------------------------
def broadcast_job_sync(job_id: str, payload: Any):
    """
    Synchronous best-effort wrapper (for sync worker code).
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # schedule in background
        asyncio.create_task(broadcast_job(job_id, payload))
    else:
        try:
            asyncio.run(broadcast_job(job_id, payload))
        except Exception as e:
            logger.debug("broadcast_job_sync failed: %s", e)


def broadcast_dm_sync(dm_id: str, payload: Any):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        asyncio.create_task(broadcast_dm(dm_id, payload))
    else:
        try:
            asyncio.run(broadcast_dm(dm_id, payload))
        except Exception as e:
            logger.debug("broadcast_dm_sync failed: %s", e)


# -------------------------
# Utilities (introspection)
# -------------------------
def get_job_subscribers_count(job_id: str) -> int:
    return len(_job_connections.get(job_id, set()))


def get_dm_subscribers_count(dm_id: str) -> int:
    return len(_dm_connections.get(dm_id, set()))
