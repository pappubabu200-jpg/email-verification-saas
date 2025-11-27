
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.app.services.bulk_ws_manager import bulk_ws_manager

router = APIRouter(prefix="/ws", tags=["websocket"])

@router.websocket("/bulk/{job_id}")
async def bulk_job_ws(websocket: WebSocket, job_id: int):
    await bulk_ws_manager.connect(job_id, websocket)

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        bulk_ws_manager.disconnect(job_id, websocket)
