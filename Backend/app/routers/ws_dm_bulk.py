from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.services.dm_bulk_ws_manager import dm_bulk_ws_manager

router = APIRouter()

@router.websocket("/ws/dm/bulk/{job_id}")
async def ws_dm_bulk(ws: WebSocket, job_id: str):
    await dm_bulk_ws_manager.connect(job_id, ws)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        await dm_bulk_ws_manager.disconnect(job_id, ws)
