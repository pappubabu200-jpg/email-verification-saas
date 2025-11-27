# backend/app/workers/admin_metrics_live.py

import asyncio
import logging
from backend.app.services.admin_ws_manager import admin_ws_manager
from backend.app.services.analytics import (
    get_total_credits,
    get_last_verifications_series,
    get_deliverability_score,
    get_recent_actions,
)

logger = logging.getLogger(__name__)

async def admin_metrics_loop():
    """Runs forever and pushes metrics to all admin dashboard clients."""
    while True:
        try:
            data = {
                "event": "metrics",
                "credits": await get_total_credits(),
                "verifications": await get_last_verifications_series(limit=20),
                "deliverability": await get_deliverability_score(),
                "events": await get_recent_actions(limit=10),
            }
            await admin_ws_manager.broadcast(data)

        except Exception as e:
            logger.exception(f"Admin metrics broadcast error: {e}")

        await asyncio.sleep(3)  # push interval
