# backend/app/routers/admin_ws.py

from fastapi import APIRouter, WebSocket, Depends, HTTPException, status
from backend.app.services.admin_ws_manager import admin_ws_manager
from backend.app.middleware.api_key_guard import get_current_user_admin
# OR your admin auth dependency

router = APIRouter()

@router.websocket("/ws/admin/metrics")
async def admin_metrics_ws(websocket: WebSocket):
    # Optional: Require admin user
    # user = await get_current_user_admin(websocket)
    # if not user.is_admin:
    #     raise HTTPException(status_code=403, detail="Not admin")

    await admin_ws_manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()  # keep alive, ignore payload
    except:
        pass
    finally:
        await admin_ws_manager.disconnect(websocket)
