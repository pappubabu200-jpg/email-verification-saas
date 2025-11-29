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

# backend/app/routers/ws_verification.py
import os
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status, HTTPException
from jose import jwt, JWTError

# Expect ws_broker to be an aioredis-backed pubsub abstraction that exposes:
# - subscribe(channel: str) -> AsyncIterator[dict|string]
# - unsubscribe(channel: str) -> None (optional)
# - publish(channel: str, payload: dict) -> None (optional)
# Adapt the subscribe calls below to your ws_broker interface if it differs.
from backend.app.services.ws_broker import ws_broker  # must exist
from backend.app.db import get_db  # optional; not used here but handy for future auth checks

logger = logging.getLogger(__name__)
router = APIRouter()

# JWT config — match your env
SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret-in-prod")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def verify_token_and_get_sub(token: str) -> dict:
    """
    Decode JWT and return the payload.
    Caller must handle JWTError.
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload


async def _forward_pubsub_to_ws(ws: WebSocket, channel: str, stop_event: asyncio.Event):
    """
    Continuously receive messages from ws_broker.subscribe(channel)
    and send them to the websocket client. Stops when stop_event is set.
    """
    try:
        sub = ws_broker.subscribe(channel)
    except Exception as exc:
        logger.exception("ws_broker.subscribe failed for %s: %s", channel, exc)
        return

    # If subscribe returns an async iterator
    try:
        async for raw in sub:
            if stop_event.is_set():
                break
            try:
                # Ensure we send JSON string
                if isinstance(raw, (dict, list)):
                    text = json.dumps(raw)
                else:
                    text = str(raw)
                await ws.send_text(text)
            except Exception as e:
                logger.debug("Failed to send message to ws client: %s", e)
                # If client disconnected the send will raise; break out so cleanup can happen
                break
    except Exception as exc:
        logger.exception("Error while reading from pubsub channel %s: %s", channel, exc)
    finally:
        # best-effort unsubscribe
        try:
            if hasattr(ws_broker, "unsubscribe"):
                await ws_broker.unsubscribe(channel)
        except Exception:
            pass


@router.websocket("/ws/verification/{user_id}")
async def verification_socket(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for a user's verification stream.

    Expected header:
      Authorization: Bearer <JWT>

    Behavior:
      - Validate JWT; require subject (sub) to equal user_id OR role==='admin'
      - Subscribe to:
          - user channel: f"user:{user_id}:verification"
          - optionally a global channel "verification:global" (if you want broadcast)
      - Forward pubsub messages to the connected websocket client
      - When client sends any message, keep-alive (we ignore client messages)
    """
    # Accept connection first (we can accept then validate headers to allow browsers)
    await websocket.accept()

    # Authorization header from WS handshake:
    # starlette/fasitapi places headers in websocket.headers
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    token = auth.replace("Bearer ", "").strip()
    try:
        payload = verify_token_and_get_sub(token)
    except JWTError as exc:
        logger.debug("Invalid token in WS connection: %s", exc)
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    # simple authorization: allow if sub equals user_id or role is admin
    sub = str(payload.get("sub", ""))
    role = payload.get("role", "")
    if sub != str(user_id) and role != "admin":
        logger.debug("WS auth failure: token sub=%s requested user=%s role=%s", sub, user_id, role)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Build list of channels to subscribe to
    user_channel = f"user:{user_id}:verification"
    global_channel = "verification:global"  # optional global stream (admin/dashboard)
    # You can also subscribe to f"user:{user_id}:notifications" etc.

    stop_event = asyncio.Event()
    forward_tasks = []

    # subscribe to user channel
    try:
        t1 = asyncio.create_task(_forward_pubsub_to_ws(websocket, user_channel, stop_event))
        forward_tasks.append(t1)
    except Exception as exc:
        logger.exception("Failed to start forward task for %s: %s", user_channel, exc)

    # subscribe to global channel (optional)
    try:
        t2 = asyncio.create_task(_forward_pubsub_to_ws(websocket, global_channel, stop_event))
        forward_tasks.append(t2)
    except Exception:
        # if global channel subscription fails, ignore
        pass

    # Main receive loop — keep socket open and react to client pings if any
    try:
        while True:
            try:
                # We wait for any client message (keeps connection alive from client's side)
                msg = await websocket.receive_text()
                # ignore payload content — we might support client-initiated actions later
                # echo heartbeat optional:
                if msg == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))
            except asyncio.CancelledError:
                break
            except WebSocketDisconnect:
                break
            except Exception:
                # on receive error, continue — the forward tasks will handle sending errors
                await asyncio.sleep(0.1)
                continue
    finally:
        # tear down forwarders
        stop_event.set()
        for t in forward_tasks:
            if not t.done():
                t.cancel()
        # best-effort close
        try:
            await websocket.close()
        except Exception:
            pass



