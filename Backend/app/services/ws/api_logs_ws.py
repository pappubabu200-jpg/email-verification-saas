# Backend/app/services/ws/api_logs_ws.py
import json
import asyncio
from typing import Set, Dict
from fastapi import WebSocket

class APILogsWSManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        # accept then add
        await ws.accept()
        async with self.lock:
            self.active.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, payload: Dict):
        """
        payload: arbitrary dict describing the API log event
        """
        text = json.dumps(payload, default=str)
        async with self.lock:
            dead = []
            for ws in set(self.active):
                try:
                    await ws.send_text(text)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.active.discard(ws)

# singleton instance
api_logs_ws = APILogsWSManager()


