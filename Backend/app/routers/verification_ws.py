#### verification_ws.py
# backend/app/routers/verification_ws.py
"""
FastAPI websocket router that forwards Redis pubsub messages to WebSocket clients.

- Endpoint: /ws/verification/{user_id}
- Auth: expects `Authorization: Bearer <token>` header. Token is JWT using same SECRET_KEY/ALGORITHM as auth.
  It verifies token and ensures token.sub == user_id OR token has role 'admin'. If not, closes connection.

Notes:
- This router subscribes to Redis channel `user:{user_id}:verification`.
- When Redis publishes JSON strings, they are forwarded to connected WS client.
"""

import os
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi import status
from jose import jwt, JWTError
import asyncio

from backend.app.services.ws_broker import ws_broker

router = APIRouter()
logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET", "replace-this-secret-in-prod")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


async def _validate_token_for_user(token: str, user_id: str) -> bool:
    """
    Return True if token is valid and either:
      - token.sub == user_id OR
      - token contains role == 'admin'
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return False

    sub = str(payload.get("sub", ""))
    role = payload.get("role")
    if sub == str(user_id):
        return True
    if role and role == "admin":
        return True
    return False


@router.websocket("/ws/verification/{user_id}")
async def verification_ws_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for a user's verification stream.
    Requires Authorization header: Bearer <token>
    """
    # Basic auth extraction (WebSocket handshake headers)
    auth = websocket.headers.get("authorization") or websocket.query_params.get("token") or ""
    token = ""
    if auth.startswith("Bearer "):
        token = auth.replace("Bearer ", "").strip()
    elif auth:
        token = auth.strip()

    # validate
    if not token or not await _validate_token_for_user(token, user_id):
        try:
            await websocket.close(code=4403)
        except Exception:
            pass
        return

    # accept WS
    await websocket.accept()

    redis = ws_broker.get_redis()
    pubsub = redis.pubsub()
    channel = f"user:{user_id}:verification"

    await pubsub.subscribe(channel)

    try:
        # spawn a background reader that waits for messages from redis and forwards them.
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                # message is usually a dict with 'type' and 'data' (data is string)
                data = message.get("data")
                try:
                    # data should be a JSON string
                    payload = data if isinstance(data, str) else str(data)
                    # ensure valid JSON, but forward raw string if json.loads fails
                    try:
                        obj = json.loads(payload)
                    except Exception:
                        obj = payload
                    await websocket.send_text(json.dumps({"from": channel, "payload": obj}))
                except Exception as e:
                    logger.exception("Failed to forward ws message: %s", e)

            # keep-alive ping from client to keep connection open or check for incoming messages
            try:
                # This will raise if client sent data or closed connection; we ignore payload and continue.
                await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                # If received any text, we simply ignore it (clients can send pings)
            except asyncio.TimeoutError:
                # no client message, continue
                pass
            except WebSocketDisconnect:
                raise
            except Exception:
                # ignore other receive errors and continue reading redis
                pass

    except WebSocketDisconnect:
        logger.debug("Verification WS client disconnected: %s", user_id)
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass
