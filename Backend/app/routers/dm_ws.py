
# backend/app/routers/dm_ws.py
"""
Decision Maker WebSocket Router
---------------------------------
WS URL:
   /ws/dm/{dm_id}

Frontend example:
   const ws = new WebSocket(`${process.env.NEXT_PUBLIC_WS_URL}/ws/dm/${id}`);

Features:
  ✓ Authenticate via Bearer token
  ✓ Join DM room (id or email)
  ✓ Receive live updates: 
        - enrich_started
        - enrich_progress
        - enrich_completed
        - enrich_failed
        - detail_ready
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from jose import jwt, JWTError
import os

from backend.app.services.dm_ws_manager import dm_ws_manager

router = APIRouter(tags=["ws:decision-maker"])


# ----------------------------------------------------
# JWT config
# ----------------------------------------------------
SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def verify_jwt(token: str):
    """
    Decode + verify token (simple version).
    You can extend this with role checks later.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=403, detail="Invalid token")


# ----------------------------------------------------
# WebSocket endpoint
# ----------------------------------------------------
@router.websocket("/ws/dm/{dm_id}")
async def dm_socket(ws: WebSocket, dm_id: str):
    """
    WebSocket for Decision Maker live events.
    - dm_id: email or numeric ID
    - Auth required via "Authorization: Bearer <token>"
    """
    # ----------------------------
    # AUTH
    # ----------------------------
    token = ws.headers.get("authorization", "")
    if not token.startswith("Bearer "):
        await ws.close(code=4403)
        return

    token = token.replace("Bearer ", "").strip()

    try:
        user = verify_jwt(token)  # returns payload
    except Exception:
        await ws.close(code=4403)
        return

    user_id = user.get("sub")
    if not user_id:
        await ws.close(code=4403)
        return

    # ----------------------------
    # CONNECT → join DM room
    # ----------------------------
    await dm_ws_manager.connect(dm_id, ws)

    # Optional: send welcome event
    try:
        await ws.send_json({
            "event": "connected",
            "dm_id": dm_id,
            "message": "Connected to Decision Maker stream"
        })
    except Exception:
        pass

    # ----------------------------
    # KEEP ALIVE LOOP
    # ----------------------------
    try:
        while True:
            # We don’t care what the client sends.
            # This keeps the WS open.
            await ws.receive_text()
    except WebSocketDisconnect:
        await dm_ws_manager.disconnect(dm_id, ws)
    except Exception:
        await dm_ws_manager.disconnect(dm_id, ws)
