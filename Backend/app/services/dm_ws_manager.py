# backend/app/services/dm_bulk_ws_manager.py
"""
Decision Maker Bulk WebSocket Manager (Redis Pub/Sub)
---------------------------------------------------
Manages live sockets for bulk DM events (e.g., job progress/completion).

- **Room:** Based on job_id.
- **Broadcast:** Uses ws_broker (Redis Pub/Sub) to send messages,
  enabling cross-process communication (e.g., from Celery workers).
"""
from typing import Dict, List, Any
from fastapi import WebSocket, WebSocketDisconnect
import logging
import asyncio
import json

# Assuming ws_broker is an importable service configured for Redis Pub/Sub
# For this file to work, you must have a 'ws_broker' module with
# 'subscribe', 'publish', and 'unsubscribe' methods.
# For example: from backend.app.services.ws_broker import ws_broker
# NOTE: The provided context includes 'from backend.app.services.ws_broker import ws_broker'
# but does not define 'ws_broker', so we will assume it exists.
from backend.app.services.ws_broker import ws_broker

logger = logging.getLogger(__name__)


class DMBulkWSManager:
    """
    Manages WebSocket connections and links them to Redis Pub/Sub channels
    based on the job_id.
    """
    def __init__(self):
        # Maps: job_id -> List[WebSocket]
        # Stores the currently connected sockets for each job.
        self.connections: Dict[str, List[WebSocket]] = {}
        # Maps: job_id -> bool
        # Tracks if a Redis listener task is already running for a job_id.
        self._listener_running: Dict[str, bool] = {}
        self._lock = asyncio.Lock()

    async def connect(self, job_id: str, ws: WebSocket):
        """
        Accepts a new WebSocket connection and starts the Redis listener
        for the given job_id if it's not already running.
        """
        await ws.accept()

        async with self._lock:
            # Add the new WebSocket to the list for this job_id
            self.connections.setdefault(job_id, []).append(ws)

            # Start the Redis listener only if it's not already running
            if not self._listener_running.get(job_id):
                self._listener_running[job_id] = True
                # Run the listener as a background task
                asyncio.create_task(self._redis_listener_task(job_id))
                logger.info(f"[DM-Bulk-WS] Started Redis listener for job {job_id}")

        logger.info(f"[DM-Bulk-WS] Client joined job {job_id}. Total: {len(self.connections[job_id])}")

    async def disconnect(self, job_id: str, ws: WebSocket):
        """
        Removes a disconnected WebSocket and handles cleanup.
        """
        async with self._lock:
            conns = self.connections.get(job_id)
            if conns and ws in conns:
                conns.remove(ws)
            
            # If no more connections for this job, the Redis listener
            # will automatically stop upon receiving this information
            # through the `unsubscribe` mechanism (handled in _redis_listener_task).
            if conns and not conns:
                self.connections.pop(job_id, None)
                # The listener task will monitor for this state and clean itself up.

        logger.info(f"[DM-Bulk-WS] Client left job {job_id}")

    async def _safe_send(self, ws: WebSocket, payload: dict):
        """
        Safely sends JSON data to a WebSocket, handling disconnects.
        """
        try:
            await ws.send_json(payload)
        except WebSocketDisconnect:
            # Let the cleanup logic handle the actual removal
            # The broadcast handler will call disconnect for full cleanup.
            # No need to await disconnect here as it would block the main loop.
            pass
        except Exception:
            logger.exception("[DM-Bulk-WS] WS send error; marking client for drop")

    async def _redis_listener_handler(self, job_id: str, payload: Dict[str, Any]):
        """
        Handler function called by ws_broker when a message is received from Redis.
        It broadcasts the message to all connected WebSockets for the job_id.
        """
        # Take a copy of the connection list to iterate over safely
        async with self._lock:
            conns = list(self.connections.get(job_id, []))

        if not conns:
            return

        dropped_websockets = []
        coros = []

        for ws in conns:
            try:
                # Add send coroutine to the list
                coros.append(ws.send_json(payload))
            except WebSocketDisconnect:
                # Handle disconnect locally if a connection failed just before sending
                dropped_websockets.append(ws)
            except Exception:
                logger.exception(f"[DM-Bulk-WS] Error sending to WS for job {job_id}. Dropping client.")
                dropped_websockets.append(ws)
                
        # Run all send operations concurrently
        await asyncio.gather(*coros, return_exceptions=True)

        # Clean up any connections that caused an exception during send
        for ws_to_drop in dropped_websockets:
             # Use the established disconnect method for full cleanup
            await self.disconnect(job_id, ws_to_drop)


    async def _redis_listener_task(self, job_id: str):
        """
        The main Redis subscription loop task.
        """
        channel = f"dm_bulk:{job_id}"
        
        # Subscribe to the channel with a partial handler to pass the job_id
        # We wrap the actual handler to automatically receive the payload
        handler_fn = lambda payload: self._redis_listener_handler(job_id, payload)
        
        await ws_broker.subscribe(channel, handler_fn)
        
        # The subscription logic in ws_broker should ideally block/loop here.
        # This task will run until the channel is explicitly unsubscribed 
        # (by the ws_broker when all handlers are removed) or until the app shuts down.

        # --- Listener Shutdown Logic (Best-effort) ---
        # A proper ws_broker implementation should handle a persistent listen.
        # If the ws_broker is designed to run until unsubscribed,
        # we need a way to detect when no one is listening on this side.

        while True:
            await asyncio.sleep(5) # Periodically check connections

            async with self._lock:
                is_connected = bool(self.connections.get(job_id))
            
            if not is_connected:
                # No more clients for this job, shut down the listener and unsubscribe
                await ws_broker.unsubscribe(channel, handler_fn)
                async with self._lock:
                    self._listener_running.pop(job_id, None)
                logger.info(f"[DM-Bulk-WS] Stopped Redis listener for job {job_id} (no clients left)")
                break


    async def broadcast(self, job_id: str, message: dict):
        """
        Publish a message to the Redis channel for the given job_id.
        This is the method called by services or workers (via `push_sync` wrapper
        if needed in a sync context).
        """
        channel = f"dm_bulk:{job_id}"
        # The message is published to Redis, and all listeners in all processes
        # will pick it up and broadcast to their local clients.
        try:
            await ws_broker.publish(channel, message)
            logger.debug(f"[DM-Bulk-WS] Published message to Redis channel {channel}")
        except Exception:
            logger.exception(f"[DM-Bulk-WS] Failed to publish message to Redis channel {channel}")


    # ------------------------------------------------------
    # Safe sync-style push (for worker usage)
    # ------------------------------------------------------
    def push_sync(self, job_id: str, payload: dict):
        """
        Synchronous best-effort wrapper (for sync worker code like Celery).
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Schedule in background if an event loop is already running (e.g., in FastAPI)
            asyncio.create_task(self.broadcast(job_id, payload))
        else:
            try:
                # Run in a new event loop (e.g., from a sync worker like Celery)
                asyncio.run(self.broadcast(job_id, payload))
            except Exception as e:
                logger.debug(f"[DM-Bulk-WS] push_sync failed for job {job_id}: {e}")


# Create manager instance
dm_bulk_ws_manager = DMBulkWSManager()
