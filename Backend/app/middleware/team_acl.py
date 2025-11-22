
# backend/app/middleware/team_acl.py
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from backend.app.utils.security import decode_token
from backend.app.services.team_context import get_user_team
from backend.app.models.user import User
from backend.app.db import SessionLocal


class TeamACL(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        Resolves:
        - request.state.team_id
        - request.state.team_role
        """
        # Not auth routes → continue
        if request.url.path.startswith("/api/v1/auth"):
            return await call_next(request)

        token = request.headers.get("Authorization")
        if not token:
            return await call_next(request)

        try:
            token = token.replace("Bearer ", "")
            payload = decode_token(token)
            user_id = int(payload.get("sub"))
        except Exception:
            return await call_next(request)

        # fetch user
        db = SessionLocal()
        try:
            user = db.query(User).get(user_id)
            if not user:
                return await call_next(request)
        finally:
            db.close()

        try:
            team_id, role = get_user_team(user_id)
        except Exception:
            team_id, role = None, None

        request.state.team_id = team_id
        request.state.team_role = role

        return await call_next(request)
