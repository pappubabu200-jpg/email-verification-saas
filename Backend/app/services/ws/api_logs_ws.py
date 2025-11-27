# Backend/app/services/ws/api_logs_ws.py
import json
import asyncio
from typing import Set, Dict
from fastapi import WebSocket

from backend.app.services.ws.api_logs_pubsub import publish_api_log

class APILogsWSManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.active.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, payload: Dict):
        """
        This is called ONLY by Redis subscriber.
        """
        text = json.dumps(payload)
        async with self.lock:
            dead = []
            for ws in list(self.active):
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.active.discard(ws)


api_logs_ws = APILogsWSManager()
