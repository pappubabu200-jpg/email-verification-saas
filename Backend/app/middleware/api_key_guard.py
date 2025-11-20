# backend/app/middleware/api_key_guard.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from backend.app.db import SessionLocal
from backend.app.services.api_key_service import get_api_key, increment_usage
from backend.app.services.usage_service import log_usage

class ApiKeyGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = request.headers.get("X-API-Key")

        if api_key:
            db = SessionLocal()
            try:
                try:
                    ak = get_api_key(db, api_key)  # may raise HTTPException(401) or 403
                except HTTPException as e:
                    return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

                # Attach to request.state
                request.state.api_user_id = ak.user_id
                request.state.api_key = api_key
                request.state.api_key_row = ak

                # Enforce per-key daily usage (atomic increment + check)
                try:
                    increment_usage(db, ak, amount=1)
                except HTTPException as e:
                    # e.g., daily limit exceeded
                    return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
                except Exception as e:
                    # DB or other problem; permissive: allow but log
                    # (we do not want to block customers when DB is flaky)
                    pass

            finally:
                db.close()

            # call the request
            response = await call_next(request)

            # Log usage asynchronously (best-effort)
            try:
                user = getattr(request.state, "api_user", None)
                # if middleware didn't set user object, we will leave it None; log_usage expects user object
                # but our earlier log_usage uses user.id; to avoid issues, we pass ak.user_id via a light wrapper
                log_usage_wrapper(request, response.status_code, ak)
            except Exception:
                pass

            return response

        # No API key - proceed normally (JWT auth will be enforced by endpoints)
        response = await call_next(request)
        return response


def log_usage_wrapper(request: Request, status_code: int, ak):
    """
    Simple wrapper to call usage_service.log_usage with DB user object minimal shape.
    This avoids forcing the middleware to load full User object here.
    """
    try:
        from backend.app.services.usage_service import log_usage
        # create a tiny object with id property to satisfy log_usage signature
        class TinyUser:
            def __init__(self, uid):
                self.id = uid
        user_obj = TinyUser(ak.user_id)
        log_usage(user_obj, ak, request, status_code)
    except Exception:
        pass
