# Backend/app/services/ws/webhook_ws.py
import json
from fastapi import WebSocket
import asyncio
from typing import Set

class WebhookEventsWSManager:
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

    async def broadcast(self, event: dict):
        msg = json.dumps({"type": "webhook_event", "data": event})
        async with self.lock:
            dead = []
            for ws in self.active:
                try:
                    await ws.send_text(msg)
                except:
                    dead.append(ws)
            for ws in dead:
                self.active.remove(ws)

webhook_ws = WebhookEventsWSManager()
