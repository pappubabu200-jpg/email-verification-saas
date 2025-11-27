# backend/app/services/admin_ws_manager.py

from typing import Dict, Set
from fastapi import WebSocket
import asyncio
import json

class AdminWSManager:
    def __init__(self):
        self.clients: Set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            self.clients.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self.lock:
            if websocket in self.clients:
                self.clients.remove(websocket)

    async def broadcast(self, data: dict):
        msg = json.dumps(data)
        disconnected = []

        for ws in self.clients:
            try:
                await ws.send_text(msg)
            except Exception:
                disconnected.append(ws)

        # remove closed sockets
        async with self.lock:
            for ws in disconnected:
                if ws in self.clients:
                    self.clients.remove(ws)


admin_ws_manager = AdminWSManager()
