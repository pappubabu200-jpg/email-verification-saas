# backend/app/services/verification_ws_manager.py

from typing import Dict, List
from fastapi import WebSocket

class VerificationWSManager:
    def __init__(self):
        # { user_id: [WebSocket1, WebSocket2, ...] }
        self.active: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()

        if user_id not in self.active:
            self.active[user_id] = []

        self.active[user_id].append(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active:
            if websocket in self.active[user_id]:
                self.active[user_id].remove(websocket)

            if not self.active[user_id]:
                del self.active[user_id]

    async def push(self, user_id: int, data: dict):
        """Send real-time updates to a specific user."""
        if user_id not in self.active:
            return

        dead = []
        message = data

        for ws in self.active[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        # cleanup dead sockets
        for ws in dead:
            self.active[user_id].remove(ws)

# backend/app/services/verification_ws_manager.py
"""
Light wrapper used by backend workers to push notifications to user channels.
Workers can call:
    import asyncio
    asyncio.run(verification_ws.push(user_id, payload))
or call ws_broker.publish directly.
"""

from typing import Any, Optional
from backend.app.services.ws_broker import ws_broker

class VerificationWS:
    def __init__(self):
        pass

    async def push(self, user_id: Optional[int], payload: Any) -> None:
        """
        Push a payload to a user's verification channel.
        Channel convention: user:{user_id}:verification
        """
        if user_id is None:
            return
        channel = f"user:{int(user_id)}:verification"
        await ws_broker.publish(channel, payload)


verification_ws = VerificationWS()


