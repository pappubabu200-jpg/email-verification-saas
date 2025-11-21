# backend/app/middleware/team_context.py
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from backend.app.services.team_service import is_user_member_of_team

class TeamContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        If client sends X-Team-Id header, validate membership and attach to request.state.team_id
        """
        team_id = request.headers.get("X-Team-Id")
        if team_id:
            try:
                team_id_int = int(team_id)
                # require request.state contains user id (set by auth middleware). We attempt to read it.
                user = getattr(request.state, "api_user_id", None)
                # If not API-key flow, user will be loaded by get_current_user in endpoints; skip heavy validation here.
                if user:
                    ok = is_user_member_of_team(user, team_id_int)
                    if ok:
                        request.state.team_id = team_id_int
                    else:
                        # do not block here; endpoints should enforce team membership
                        request.state.team_id = None
                else:
                    request.state.team_id = None
            except Exception:
                request.state.team_id = None
        return await call_next(request)
