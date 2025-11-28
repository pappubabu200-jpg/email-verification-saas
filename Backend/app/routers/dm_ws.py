
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

# backend/app/routers/dm_ws.py

"""
Decision Maker WebSocket Router
--------------------------------
Provides:
 - /ws/dm/job/{job_id}  → Autodiscovery live events
 - /ws/dm/{dm_id}       → Single decision maker enrichment events

Uses:
   dm_ws_manager.connect_job
   dm_ws_manager.connect_dm
   dm_ws_manager.disconnect_job
   dm_ws_manager.disconnect_dm
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from backend.app.services.dm_ws_manager import (
    connect_job,
    disconnect_job,
    connect_dm,
    disconnect_dm,
)
from backend.app.services.security import decode_access_token  # optional auth check
import logging

router = APIRouter(tags=["ws-dm"])
logger = logging.getLogger(__name__)


# -------------------------------------------------------------
# Optional token extraction
# -------------------------------------------------------------
def _extract_bearer_token(ws: WebSocket):
    """
    Extract token from websocket headers. Optional.
    If you want strict authentication, enforce it below.
    """
    auth = ws.headers.get("authorization") or ""
    if auth.startswith("Bearer "):
        return auth.replace("Bearer ", "").strip()
    return None


# -------------------------------------------------------------
# Autodiscovery Job Stream
# -------------------------------------------------------------
@router.websocket("/ws/dm/job/{job_id}")
async def ws_dm_job(websocket: WebSocket, job_id: str):
    # Optional auth
    token = _extract_bearer_token(websocket)
    if token:
        try:
            decode_access_token(token)  # throws if invalid
        except Exception:
            await websocket.close(code=4403)
            return

    # Accept & register connection
    await connect_job(websocket, job_id)

    logger.info(f"WS connected: job={job_id}")

    try:
        while True:
            # Keep-alive (client doesn't need to send anything)
            await websocket.receive_text()

    except WebSocketDisconnect:
        await disconnect_job(websocket, job_id)
        logger.info(f"WS disconnected: job={job_id}")

    except Exception as e:
        logger.error(f"WebSocket error on job {job_id}: {e}")
        await disconnect_job(websocket, job_id)
        try:
            await websocket.close()
        except:
            pass


# -------------------------------------------------------------
# Single Decision Maker Live Enrichment Stream
# -------------------------------------------------------------
@router.websocket("/ws/dm/{dm_id}")
async def ws_dm_single(websocket: WebSocket, dm_id: str):
    # Optional auth
    token = _extract_bearer_token(websocket)
    if token:
        try:
            decode_access_token(token)
        except Exception:
            await websocket.close(code=4403)
            return

    # Accept connection
    await connect_dm(websocket, dm_id)

    logger.info(f"WS connected: dm={dm_id}")

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        await disconnect_dm(websocket, dm_id)
        logger.info(f"WS disconnected: dm={dm_id}")

    except Exception as e:
        logger.error(f"WS error on dm {dm_id}: {e}")
        await disconnect_dm(websocket, dm_id)
        try:
            await websocket.close()
        except:
            pass



