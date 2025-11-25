# backend/app/middleware/api_key_guard.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

from backend.app.db import SessionLocal
from backend.app.services.api_key_service import get_api_key, increment_usage
from backend.app.services.usage_service import log_usage


class APIKeyGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = request.headers.get("X-API-Key")

        # If request has API key
        if api_key:
            db = SessionLocal()
            ak = None

            try:
                # Validate API key
                try:
                    ak = get_api_key(db, api_key)
                except HTTPException as e:
                    db.close()
                    return JSONResponse(
                        status_code=e.status_code,
                        content={"detail": e.detail},
                    )

                # Attach minimal metadata to request
                request.state.api_key = api_key
                request.state.api_key_row = ak
                request.state.api_user_id = ak.user_id

                # Create tiny user object for usage logging
                class TinyUser:
                    def __init__(self, uid):
                        self.id = uid

                request.state.api_user = TinyUser(ak.user_id)

                # Enforce per-key usage limit (daily)
                try:
                    increment_usage(db, ak, amount=1)
                except HTTPException as e:
                    db.close()
                    return JSONResponse(
                        status_code=e.status_code,
                        content={"detail": e.detail},
                    )
                except Exception:
                    # log but do not block user
                    pass

            finally:
                db.close()

            # Forward request
            response = await call_next(request)

            # Log usage (non-blocking)
            try:
                self._safe_log_usage(request, response)
            except Exception:
                pass

            return response

        # No API key → normal JWT flow
        return await call_next(request)

    def _safe_log_usage(self, request, response):
        """Wrapper to call usage logging in a safe manner."""
        try:
            user = getattr(request.state, "api_user", None)
            ak = getattr(request.state, "api_key_row", None)

            if user and ak:
                log_usage(user, ak, request, response.status_code)
        except Exception:
            pass
