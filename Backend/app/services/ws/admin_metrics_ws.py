
# Backend/app/services/ws/admin_metrics_ws.py
import json
from typing import Dict, Set
from fastapi import WebSocket
import asyncio

class AdminMetricsWSManager:
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
        msg = json.dumps(payload)
        async with self.lock:
            dead = []
            for ws in self.active:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.active.remove(ws)


admin_metrics_ws = AdminMetricsWSManager()
