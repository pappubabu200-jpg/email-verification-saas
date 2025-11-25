# backend/app/middleware/audit_middleware.py
import asyncio
import time
from datetime import datetime
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from backend.app.db import SessionLocal

# try to import your repo helper — expected: create_audit_log(db, payload_dict)
try:
    from backend.app.repositories.audit_log_repository import create_audit_log
except Exception:
    create_audit_log = None  # we'll fallback to safe no-op if missing


def _client_ip_from_request(request: Request) -> str:
    # Prefer X-Forwarded-For (if behind proxy), else request.client.host
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # may contain comma separated list
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Non-blocking audit logger middleware.
    Writes one audit row per request (best-effort).
    """

    async def dispatch(self, request: Request, call_next):
        # Skip trivial endpoints
        path = request.url.path or "/"
        if path.startswith("/health") or path.startswith("/docs") or path.startswith("/openapi.json") or path.startswith("/static"):
            return await call_next(request)

        start = time.time()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Still attempt to log the error/failed request, then re-raise
            status_code = 500
            duration_ms = int((time.time() - start) * 1000)
            await self._schedule_audit(request, status_code, duration_ms, error=str(exc))
            raise

        duration_ms = int((time.time() - start) * 1000)
        status_code = getattr(response, "status_code", 0)

        # Schedule an async audit write (fire-and-forget)
        try:
            await self._schedule_audit(request, status_code, duration_ms)
        except Exception:
            # never crash the request due to auditing
            pass

        return response

    async def _schedule_audit(self, request: Request, status_code: int, duration_ms: int, error: Optional[str] = None):
        """
        Create an audit payload and schedule a background write using asyncio.to_thread
        so we don't block the async request loop.
        """
        payload = {
            "timestamp": datetime.utcnow(),
            "method": request.method,
            "path": request.url.path,
            "query_string": request.url.query or None,
            "status_code": int(status_code),
            "duration_ms": duration_ms,
            "client_ip": _client_ip_from_request(request),
            "user_agent": request.headers.get("user-agent"),
            "referrer": request.headers.get("referer") or request.headers.get("referrer"),
            "error": error,
            # best-effort metadata from other middleware/services:
            "user_id": getattr(getattr(request, "state", None), "user", None) and getattr(request.state.user, "id", None) or getattr(request.state, "api_user_id", None),
            "team_id": getattr(getattr(request, "state", None), "team", None) and getattr(request.state.team, "id", None) or getattr(request.state, "team_id", None),
            "api_key_id": getattr(getattr(request, "state", None), "api_key_row", None) and getattr(request.state.api_key_row, "id", None),
        }

        # schedule the DB write in a thread so it doesn't block the event loop
        # use asyncio.to_thread for Python 3.9+. If unavailable, fallback to create_task with a coroutine wrapper.
        try:
            await asyncio.to_thread(_write_audit_entry, payload)
        except AttributeError:
            # older python fallback
            asyncio.create_task(_write_audit_entry_async(payload))


def _write_audit_entry(payload: dict):
    """
    Synchronous writer executed in a worker thread.
    Tries to use the repository helper if present; otherwise it will attempt a minimal insert.
    """
    db = SessionLocal()
    try:
        if create_audit_log:
            try:
                create_audit_log(db, payload)
                return
            except Exception:
                # Fall through to minimal insert on failure
                pass

        # If repository helper isn't available or failed, do a minimal raw insert.
        # This expects you have an audit_log table with columns matching keys used.
        try:
            # Use SQLAlchemy Core if available on SessionLocal (best-effort — adapt if your session API differs)
            # -> Keep this minimal and tolerant to schema differences.
            db.execute(
                """
                INSERT INTO audit_log (timestamp, method, path, query_string, status_code, duration_ms, client_ip, user_agent, referrer, error, user_id, team_id, api_key_id)
                VALUES (:timestamp, :method, :path, :query_string, :status_code, :duration_ms, :client_ip, :user_agent, :referrer, :error, :user_id, :team_id, :api_key_id)
                """,
                {
                    "timestamp": payload.get("timestamp"),
                    "method": payload.get("method"),
                    "path": payload.get("path"),
                    "query_string": payload.get("query_string"),
                    "status_code": payload.get("status_code"),
                    "duration_ms": payload.get("duration_ms"),
                    "client_ip": payload.get("client_ip"),
                    "user_agent": payload.get("user_agent"),
                    "referrer": payload.get("referrer"),
                    "error": payload.get("error"),
                    "user_id": payload.get("user_id"),
                    "team_id": payload.get("team_id"),
                    "api_key_id": payload.get("api_key_id"),
                },
            )
            db.commit()
        except Exception:
            # Last resort: swallow errors. Auditing must be best-effort only.
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        try:
            db.close()
        except Exception:
            pass


async def _write_audit_entry_async(payload: dict):
    """Coroutine wrapper used when to_thread isn't available."""
    await asyncio.get_running_loop().run_in_executor(None, _write_audit_entry, payload)
