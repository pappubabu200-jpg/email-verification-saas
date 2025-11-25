# backend/app/middleware/team_acl.py

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from backend.app.db import SessionLocal
from backend.app.repositories.team_repository import (
    get_team_role_for_user,
    is_user_member_of_team,
)


"""
TeamACL Middleware (Final Version)

Requires:
- request.state.team_id  (set by TeamContextMiddleware)
- request.state.user.id OR request.state.api_user_id

Adds:
    request.state.team_role      (owner/admin/member/viewer/billing)
    request.state.team_perms     (dict of boolean permissions)

This middleware DOES NOT:
- decode JWT
- override team_id
- revalidate team_context
- block the request unless membership is invalid

Actual permission blocking is done by endpoints or a decorator.
"""


class TeamACL(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path or "/"

        # Skip non-team-sensitive routes
        if (
            path.startswith("/api/v1/auth")
            or path.startswith("/health")
            or path.startswith("/metrics")
        ):
            return await call_next(request)

        # TeamContextMiddleware MUST have already set this
        team_id = getattr(request.state, "team_id", None)
        if not team_id:
            return await call_next(request)

        # Identify user (API or JWT)
        user_id = (
            getattr(request.state, "api_user_id", None)
            or getattr(getattr(request.state, "user", None), "id", None)
        )

        if not user_id:
            # Anonymous users have no team permissions
            request.state.team_role = None
            request.state.team_perms = {}
            return await call_next(request)

        db = SessionLocal()

        try:
            # Check membership
            if not is_user_member_of_team(user_id, team_id):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "You are not a member of this team."},
                )

            # Load role: owner/admin/member/viewer/billing
            role = get_team_role_for_user(user_id, team_id)

            # Attach to request.state
            request.state.team_role = role

            # Compute basic permission matrix
            perms = {
                "is_owner": role == "owner",
                "is_admin": role in ("owner", "admin"),
                "is_billing": role in ("owner", "admin", "billing"),
                "can_invite": role in ("owner", "admin"),
                "can_delete_team": role == "owner",
                "can_manage_api_keys": role in ("owner", "admin"),
                "can_view_usage": role in ("owner", "admin", "member"),
                "can_manage_billing": role in ("owner", "admin", "billing"),
            }

            request.state.team_perms = perms

        except Exception as e:
            db.close()
            return JSONResponse(
                status_code=500,
                content={"detail": f"TeamACL error: {str(e)[:200]}"}
            )

        db.close()
        return await call_next(request)
