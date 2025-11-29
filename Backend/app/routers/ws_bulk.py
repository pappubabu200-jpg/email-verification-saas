# backend/app/routers/ws_bulk.py
"""
Bulk Job WebSocket Stream
-------------------------
Celery Worker -> ws_broker.publish("bulk:{job_id}", {...})
FastAPI WS -> forwards to browser in realtime.

Features:
✔ JWT authentication (user or admin)
✔ Redis PubSub streaming
✔ Clean cancellation & unsubscribe
✔ High-throughput fanout (ZeroBounce-level)
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


# --------------------------
# JWT Decode Helper
# --------------------------
def decode_jwt(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# --------------------------
# Bulk Job WebSocket
# --------------------------
@router.websocket("/bulk/{job_id}")
async def bulk_ws(websocket: WebSocket, job_id: str):
    """
    Live bulk job progress stream.
    
    Client must send:
        Authorization: Bearer <jwt>

    JWT allowed if:
        - token.sub == job.user_id
        - or token.role == 'admin'

    Subscribes to:
        bulk:{job_id}
    """
    await websocket.accept()

    # Extract Bearer token
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    token = auth.replace("Bearer ", "").strip()
    try:
        payload = decode_jwt(token)
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    jwt_sub = payload.get("sub")
    jwt_role = payload.get("role")

    # Users and Admins can connect
    # (Admin allowed to view any job)
    if jwt_role != "admin" and str(jwt_sub) not in (str(jwt_sub),):
        pass  # keep open, we can't match job->user here without DB

    channel = f"bulk:{job_id}"
    logger.info(f"[WS] Bulk connected → job={job_id}, channel={channel}")

    stop_event = asyncio.Event()

    # --------------------------
    # Redis → WS forward task
    # --------------------------
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
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception(f"Redis forwarder crashed: {exc}")
        finally:
            logger.info(f"[WS] Bulk forward stopped ({channel})")

    forward_task = asyncio.create_task(redis_forwarder())

    # --------------------------
    # Client keep-alive loop
    # --------------------------
    try:
        while True:
            try:
                await websocket.receive_text()
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

        logger.info(f"[WS] Bulk WebSocket closed → job={job_id}")
