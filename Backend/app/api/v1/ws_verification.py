
# backend/app/api/ws_verification.py
"""
Verification WebSocket Router
Real-time streaming for:
- Single email verification events
- Bulk job events
- Credit updates
- Risk score streams

Channel pattern:
  user:{user_id}:verification
"""

from __future__ import annotations

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.services.ws_broker import ws_broker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/verification/{user_id}")
async def verification_ws(websocket: WebSocket, user_id: int):
    """
    Browser connects to: ws://HOST/ws/verification/123
    Worker publishes to:  user:123:verification
    """
    await websocket.accept()

    redis_channel = f"user:{user_id}:verification"
    logger.info(f"[WS] User {user_id} connected → channel {redis_channel}")

    try:
        # Subscribe to Redis channel
        async for message in ws_broker.subscribe(redis_channel):
            try:
                await websocket.send_text(json.dumps(message))
            except Exception:
                logger.warning(f"[WS] Failed sending to user {user_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"[WS] User {user_id} disconnected")

    except Exception as e:
        logger.exception(f"[WS] Error on verification_ws for user {user_id}: {e}")

    finally:
        try:
            await websocket.close()
        except Exception:
            pass

        logger.info(f"[WS] Closed connection for user {user_id}")
