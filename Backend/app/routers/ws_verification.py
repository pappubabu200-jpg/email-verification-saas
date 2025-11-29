# backend/app/routers/ws_verification.py
"""
Verification WebSocket Router
-----------------------------
This router forwards Redis PubSub verification messages to browser WS clients.

Celery → ws_broker.publish("user:{id}:verification", {...})
FastAPI WS → subscribes → forwards → frontend
"""

from __future__ import annotations

import os
import json
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import jwt, JWTError

from backend.app.services.ws_broker import ws_broker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws"])

# JWT ENV VARS
SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret-in-prod")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


# ------------------------------
# JWT Decode Helper
# ------------------------------
def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        logger.debug("JWT decode error: %s", exc)
        raise


# ------------------------------
# WebSocket: Verification stream
# ------------------------------
@router.websocket("/verification/{user_id}")
async def verification_ws(websocket: WebSocket, user_id: str):
    """
    WebSocket → real-time verification stream for a user.

    Client must connect with:
        Authorization: Bearer <jwt>

    Allowed if:
        - JWT.sub == {user_id}  OR
        - JWT.role == "admin"

    Subscribes to Redis:
        user:{user_id}:verification
    """
    await websocket.accept()

    # -------------------------
    # AUTH CHECK
    # -------------------------
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    token = auth.replace("Bearer ", "").strip()

    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    jwt_sub = str(payload.get("sub"))
    jwt_role = payload.get("role")

    if jwt_sub != str(user_id) and jwt_role != "admin":
        logger.debug(f"WS auth denied: sub={jwt_sub}, userId={user_id}, role={jwt_role}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # -------------------------
    # REDIS CHANNEL
    # -------------------------
    channel = f"user:{user_id}:verification"
    logger.info(f"WS connected: user={user_id} → Redis channel={channel}")

    stop_event = asyncio.Event()

    # -------------------------
    # REDIS → WS forward task
    # -------------------------
    async def redis_forwarder():
        try:
            async for message in ws_broker.subscribe(channel):
                if stop_event.is_set():
                    break
                try:
                    if isinstance(message, dict):
                        await websocket.send_text(json.dumps(message, default=str))
                    else:
                        await websocket.send_text(json.dumps({"_raw": message}))
                except Exception as exc:
                    logger.debug(f"WS send failed, closing forwarder: {exc}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception(f"Redis forwarder error ({channel}): {exc}")
        finally:
            logger.info(f"Redis forwarder stopped for channel={channel}")

    forward_task = asyncio.create_task(redis_forwarder())

    # -------------------------
    # CLIENT RECEIVE LOOP
    # -------------------------
    try:
        while True:
            try:
                await websocket.receive_text()  # keep-alive / ping
            except WebSocketDisconnect:
                break
            except Exception:
                break
    finally:
        stop_event.set()
        forward_task.cancel()

        try:
            await websocket.close()
        except:
            pass

        logger.info(f"WS closed: user={user_id}, channel={channel}")
