# backend/app/routers/ws_verification.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
import os

from backend.app.services.verification_ws_manager import VerificationWSManager

router = APIRouter(prefix="/ws", tags=["WebSocket"])

SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

verification_ws = VerificationWSManager()


def decode_jwt(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


@router.websocket("/verification")
async def user_verification_socket(ws: WebSocket):

    # --------------------------
    # AUTH: Extract token
    # --------------------------
    token = ws.headers.get("authorization")
    if not token or not token.startswith("Bearer "):
        await ws.close(code=4401)
        return

    token = token.replace("Bearer ", "").strip()
    decoded = decode_jwt(token)

    if not decoded or "sub" not in decoded:
        await ws.close(code=4403)
        return

    user_id = int(decoded["sub"])

    # --------------------------
    # ACCEPT CONNECTION
    # --------------------------
    await verification_ws.connect(user_id, ws)

    try:
        while True:
            # Client may send ping messages — we ignore
            await ws.receive_text()
    except WebSocketDisconnect:
        await verification_ws.disconnect(user_id, ws)
