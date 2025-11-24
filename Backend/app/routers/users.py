
# backend/app/routers/user.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.schemas.user import UserResponse, UserUpdate
from backend.app.repositories.user_repository import UserRepository
from backend.app.repositories.usage_log_repository import UsageLogRepository
from backend.app.repositories.audit_log_repository import AuditLogRepository
from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user  # ← You will get this file next

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------
# DB Dependency
# ---------------------------------------
async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------
# GET /users/me — current logged user
# ---------------------------------------
@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user = Depends(get_current_user),
):
    """
    Returns the currently logged-in user.
    """
    return UserResponse.from_orm(current_user)


# ---------------------------------------
# PATCH /users/update — update profile
# ---------------------------------------
@router.patch("/update", response_model=UserResponse)
async def update_user(
    payload: UserUpdate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Updates user profile fields:
    - first_name
    - last_name
    - timezone
    - country
    """
    repo = UserRepository(db)
    updated = await repo.update(current_user, payload.dict(exclude_unset=True))
    return UserResponse.from_orm(updated)


# ---------------------------------------
# GET /users/credits — credit balance
# ---------------------------------------
@router.get("/credits")
async def get_user_credits(
    current_user = Depends(get_current_user),
):
    """
    Returns available user credits.
    """
    return {"credits": float(current_user.credits)}


# -----------------------------------------------
# GET /users/activity — usage + audit combined
# -----------------------------------------------
@router.get("/activity")
async def get_user_activity(
    limit: int = 50,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns recent activity:
    - verification usage logs
    - audit logs
    """
    usage_repo = UsageLogRepository(db)
    audit_repo = AuditLogRepository(db)

    usage = await usage_repo.list_user_usage(current_user.id, limit)
    audit = await audit_repo.list_user_logs(current_user.id, limit)

    return {
        "usage_logs": usage,
        "audit_logs": audit,
        "count": {
            "usage": len(usage),
            "audit": len(audit),
        }
    }
