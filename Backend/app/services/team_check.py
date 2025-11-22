# backend/app/services/acl_check.py
from fastapi import HTTPException
from backend.app.services.acl_matrix import check_permission


def require_team_permission(request, permission: str):
    """
    Call inside endpoint:
    require_team_permission(request, "can_invite")
    """
    role = getattr(request.state, "team_role", None)
    if not role:
        raise HTTPException(status_code=403, detail="no_team_role")

    ok = check_permission(role, permission)
    if not ok:
        raise HTTPException(status_code=403, detail=f"permission_denied:{permission}")


