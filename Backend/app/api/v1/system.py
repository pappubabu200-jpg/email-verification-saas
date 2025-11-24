
# backend/app/api/v1/system.py
from fastapi import APIRouter
from backend.app.db import engine
from backend.app.config import settings
import logging, socket

router = APIRouter(prefix="/api/v1/system", tags=["system"])
logger = logging.getLogger(__name__)

@router.get("/health")
def health():
    """
    Light health check: DB connectivity + Redis + service flags.
    """
    ok = {"status": "ok", "checks": {}}

    # DB check - simple engine connect
    try:
        conn = engine.connect()
        conn.execute("SELECT 1")
        conn.close()
        ok["checks"]["db"] = "ok"
    except Exception as e:
        logger.exception("db health failed")
        ok["checks"]["db"] = f"error: {str(e)[:200]}"
        ok["status"] = "degraded"

    # Redis check (best-effort)
    try:
        import redis
        from backend.app.config import settings as _s
        r = redis.from_url(_s.REDIS_URL)
        pong = r.ping()
        ok["checks"]["redis"] = "ok" if pong else "no_ping"
    except Exception as e:
        ok["checks"]["redis"] = f"error: {str(e)[:200]}"
        ok["status"] = "degraded"

    # base info
    ok["hostname"] = socket.gethostname()
    ok["version_info"] = {"uvicorn": True}
    return ok

@router.get("/ready")
def ready():
    """
    Readiness probe: more strict than health (fail if DB or Redis not ok).
    """
    h = health()
    if h["checks"].get("db") != "ok":
        return {"ready": False, "details": h}
    if h["checks"].get("redis") != "ok":
        return {"ready": False, "details": h}
    return {"ready": True}
