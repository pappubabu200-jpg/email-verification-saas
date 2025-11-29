# backend/app/routers/ws_admin_metrics.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt
import os

from backend.app.services.ws_fanout import ws_fanout

router = APIRouter()

SECRET_KEY = os.getenv("JWT_SECRET", "replace-me")
ALGORITHM = "HS256"


def verify_admin_token(token: str) -> bool:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("role") == "admin"
    except:
        return False


@router.websocket("/ws/admin/metrics")
async def ws_admin_metrics(websocket: WebSocket):

    await ws_fanout.start()

    # Authenticate
    token = websocket.headers.get("authorization")
    if not token:
        await websocket.close(code=4403)
        return

    token = token.replace("Bearer ", "").strip()

    if not verify_admin_token(token):
        await websocket.close(code=4403)
        return

    await websocket.accept()

    channel = "admin:metrics"
    await ws_fanout.subscribe_ws(channel, websocket)

    try:
        while True:
            try:
                await websocket.receive_text()
            except:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await ws_fanout.unsubscribe_ws(channel, websocket)
