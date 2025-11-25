# backend/app/middleware/team_context.py

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from backend.app.db import SessionLocal
from backend.app.services.team_service import (
    is_user_member_of_team,
    get_default_team_for_user,
    get_team_by_id,
)

"""
Team Context Middleware (Final Version)

Loads team context for each request using this priority:

1) API Key → team_id (if bound to a specific team)
2) X-Team-Id header → validate membership
3) ?team_id= query parameter → validate membership
4) Default team of the logged-in user (JWT auth)
5) Fallback → no team

Sets:
    request.state.team
    request.state.team_id

Notes:
- Never blocks the request unless invalid team membership in explicit request header
- Team ACL middleware will enforce strict permissions later
- Keeps this middleware light & fast
"""


class TeamContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path or "/"

        # Ignore non-team endpoints
        if path.startswith("/health") or path.startswith("/metrics"):
            return await call_next(request)

        db = SessionLocal()
        request.state.team = None
        request.state.team_id = None

        try:
            # -----------------------------------------------------
            # 1) API Key user → team from key
            # -----------------------------------------------------
            ak = getattr(request.state, "api_key_row", None)
            if ak and getattr(ak, "team_id", None):
                team = get_team_by_id(db, ak.team_id)
                if team:
                    request.state.team = team
                    request.state.team_id = team.id
                    db.close()
                    return await call_next(request)

            # Identify user id (API user or JWT user)
            user_id = (
                getattr(request.state, "api_user_id", None)
                or getattr(getattr(request.state, "user", None), "id", None)
            )

            # -----------------------------------------------------
            # 2) X-Team-Id header
            # -----------------------------------------------------
            header_team_id = request.headers.get("X-Team-Id")
            if header_team_id:
                try:
                    header_team_id = int(header_team_id)
                    team = get_team_by_id(db, header_team_id)
                    if team:
                        # If user_id available → validate membership
                        if user_id and not is_user_member_of_team(user_id, header_team_id):
                            return JSONResponse(
                                status_code=403,
                                content={"detail": "Not authorized for this team."},
                            )

                        request.state.team = team
                        request.state.team_id = team.id
                        db.close()
                        return await call_next(request)
                except ValueError:
                    pass  # ignore bad header format

            # -----------------------------------------------------
            # 3) Query param ?team_id=
            # -----------------------------------------------------
            query_team_id = request.query_params.get("team_id")
            if query_team_id:
                try:
                    query_team_id = int(query_team_id)
                    team = get_team_by_id(db, query_team_id)
                    if team:
                        if user_id and not is_user_member_of_team(user_id, query_team_id):
                            return JSONResponse(
                                status_code=403,
                                content={"detail": "Not authorized for this team."},
                            )

                        request.state.team = team
                        request.state.team_id = team.id
                        db.close()
                        return await call_next(request)
                except ValueError:
                    pass

            # -----------------------------------------------------
            # 4) User's default team (JWT auth)
            # -----------------------------------------------------
            if user_id:
                default_team = get_default_team_for_user(user_id)
                if default_team:
                    request.state.team = default_team
                    request.state.team_id = default_team.id
                    db.close()
                    return await call_next(request)

            # -----------------------------------------------------
            # 5) No team found → allow,
            # ACL middleware will decide if allowed later
            # -----------------------------------------------------
            request.state.team = None
            request.state.team_id = None

        except HTTPException as e:
            db.close()
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        except Exception as e:
            db.close()
            return JSONResponse(
                status_code=500, content={"detail": f"TeamContext error: {str(e)[:200]}"}
            )

        db.close()
        return await call_next(request)
