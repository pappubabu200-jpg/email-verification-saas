# backend/app/routers/ws_stream.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging

from backend.app.services.ws_broker import ws_broker

router = APIRouter(tags=["websocket-streams"])

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# BULK JOB WEBSOCKET
# ---------------------------------------------------------
@router.websocket("/ws/bulk/{job_id}")
async def bulk_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    channel = f"bulk:{job_id}"

    try:
        async for msg in ws_broker.subscribe(channel):
            await websocket.send_json(msg)

    except WebSocketDisconnect:
        logger.info(f"WS bulk {job_id} disconnected")

    except Exception as e:
        logger.error(f"WS bulk error {job_id}: {e}")


# ---------------------------------------------------------
# USER VERIFICATION STREAM
# ---------------------------------------------------------
@router.websocket("/ws/user/{user_id}/verification")
async def user_verification_ws(websocket: WebSocket, user_id: int):
    await websocket.accept()
    channel = f"user:{user_id}:verification"

    try:
        async for msg in ws_broker.subscribe(channel):
            await websocket.send_json(msg)

    except WebSocketDisconnect:
        logger.info(f"WS user {user_id} disconnected")

    except Exception as e:
        logger.error(f"WS user error: {e}")
