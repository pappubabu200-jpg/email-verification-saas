
# backend/app/services/dm_bulk_ws_manager.py
from typing import Dict, List
from fastapi import WebSocket
import asyncio
import logging

logger = logging.getLogger(__name__)

class DMBulkWSManager:
    def __init__(self):
        self.jobs: Dict[str, List[WebSocket]] = {}

    async def connect(self, job_id: str, ws: WebSocket):
        await ws.accept()
        self.jobs.setdefault(job_id, []).append(ws)
        logger.debug("WS connect %s (%d)", job_id, len(self.jobs[job_id]))

    async def disconnect(self, job_id: str, ws: WebSocket):
        conns = self.jobs.get(job_id, [])
        try:
            conns.remove(ws)
        except ValueError:
            pass
        if not conns:
            self.jobs.pop(job_id, None)

    async def broadcast_job(self, job_id: str, payload: dict):
        conns = list(self.jobs.get(job_id, []))
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                try:
                    await ws.close()
                except:
                    pass
                await self.disconnect(job_id, ws)

dm_bulk_ws_manager = DMBulkWSManager()
