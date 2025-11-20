from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.db import SessionLocal
from backend.app.services.api_key_service import get_api_key, increment_usage


class ApiKeyGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        api_key = request.headers.get("X-API-Key")

        if api_key:
            # Validate API key
            db = SessionLocal()
            key_obj = None
            try:
                # get_api_key raises HTTPException(401) if invalid
                key_obj = get_api_key(db, api_key)
                increment_usage(db, key_obj.id)
            finally:
                db.close()

            # Attach user_id and api_key to request state so downstream code can use it
            # - api_user_id: DB user id mapped to the API key
            # - api_key: the actual API key string for per-api-key limiters
            request.state.api_user_id = key_obj.user_id
            request.state.api_key = api_key

            return await call_next(request)

        # No API key? Proceed normally (JWT-based routes work)
        response = await call_next(request)
        return response
