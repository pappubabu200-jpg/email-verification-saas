# backend/app/routers/ws_fanout_router.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt
import os
import json

from backend.app.services.ws_fanout import ws_fanout

router = APIRouter()

SECRET_KEY = os.getenv("JWT_SECRET", "replace-me")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def verify_token(token: str, expected_user: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = str(payload.get("sub"))
        role = payload.get("role")
        return sub == expected_user or role == "admin"
    except:
        return False


@router.websocket("/ws/verification/{user_id}")
async def ws_verification(websocket: WebSocket, user_id: str):
    await ws_fanout.start()

    # Auth
    token = websocket.headers.get("authorization")
    if not token:
        await websocket.close(code=4403)
        return

    token = token.replace("Bearer ", "").strip()
    if not verify_token(token, user_id):
        await websocket.close(code=4403)
        return

    # Accept
    await websocket.accept()

    channel = f"user:{user_id}:verification"
    await ws_fanout.subscribe_ws(channel, websocket)

    try:
        while True:
            # receive ping from frontend to keep alive
            try:
                await websocket.receive_text()
            except:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        await ws_fanout.unsubscribe_ws(channel, websocket)
