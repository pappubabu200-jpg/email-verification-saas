from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from backend.app.utils.security import get_current_user
from backend.app.services.acl_check import require_team_permission
from backend.app.services.acl_matrix import TEAM_PERMISSIONS
from backend.app.services.team_context import get_user_team
from backend.app.db import SessionLocal

from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember, TEAM_ROLES
from backend.app.models.user import User

router = APIRouter(prefix="/api/v1/team", tags=["team"])


# ----------------------------
# Pydantic Models
# ----------------------------

class InvitePayload(BaseModel):
    email: str
    role: str = "member"


class ChangeRolePayload(BaseModel):
    user_id: int
    role: str


class RemovePayload(BaseModel):
    user_id: int


# ----------------------------
# TEAM INFO
# ----------------------------

@router.get("/info")
def team_info(request: Request, current_user=Depends(get_current_user)):
    team_id, role = get_user_team(current_user.id)

    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")

        # Count members
        member_count = db.query(TeamMember).filter(TeamMember.team_id == team_id).count()

        return {
            "team_id": team_id,
            "team_name": team.name,
            "role": role,
            "members": member_count,
            "permissions": TEAM_PERMISSIONS.get(role, {}),
        }
    finally:
        db.close()


# ----------------------------
# LIST MEMBERS
# ----------------------------

@router.get("/members")
def team_members(request: Request, current_user=Depends(get_current_user)):
    team_id, role = get_user_team(current_user.id)

    db = SessionLocal()
    try:
        rows = (
            db.query(TeamMember, User)
            .join(User, User.id == TeamMember.user_id)
            .filter(TeamMember.team_id == team_id)
            .all()
        )

        members = []
        for tm, user in rows:
            members.append({
                "user_id": tm.user_id,
                "email": user.email,
                "role": tm.role,
                "invited": tm.invited,
            })

        return {"team_id": team_id, "members": members}
    finally:
        db.close()


# ----------------------------
# INVITE MEMBER
# ----------------------------

@router.post("/invite")
def invite_member(payload: InvitePayload, request: Request, current_user=Depends(get_current_user)):
    require_team_permission(request, "can_invite")

    team_id, my_role = get_user_team(current_user.id)

    if payload.role not in TEAM_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")

    db = SessionLocal()
    try:
        # find or create user
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            # auto-create (no password yet)
            user = User(email=payload.email, hashed_password="invited", is_active=False)
            db.add(user)
            db.commit()
            db.refresh(user)

        # check if already member
        exists = (
            db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == user.id)
            .first()
        )
        if exists:
            raise HTTPException(status_code=400, detail="already_member")

        tm = TeamMember(
            team_id=team_id,
            user_id=user.id,
            role=payload.role,
            invited=True,
        )
        db.add(tm)
        db.commit()

        return {"ok": True, "user_id": user.id, "role": payload.role}
    finally:
        db.close()


# ----------------------------
# CHANGE ROLE
# ----------------------------

@router.post("/change-role")
def change_role(payload: ChangeRolePayload, request: Request, current_user=Depends(get_current_user)):
    require_team_permission(request, "can_change_role")

    team_id, my_role = get_user_team(current_user.id)

    if payload.role not in TEAM_ROLES:
        raise HTTPException(status_code=400, detail="invalid_role")

    db = SessionLocal()
    try:
        tm = (
            db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == payload.user_id)
            .first()
        )
        if not tm:
            raise HTTPException(status_code=404, detail="member_not_found")

        tm.role = payload.role
        db.commit()

        return {"ok": True, "user_id": payload.user_id, "new_role": payload.role}
    finally:
        db.close()


# ----------------------------
# REMOVE MEMBER
# ----------------------------

@router.post("/remove")
def remove_member(payload: RemovePayload, request: Request, current_user=Depends(get_current_user)):
    require_team_permission(request, "can_remove")

    team_id, my_role = get_user_team(current_user.id)

    db = SessionLocal()
    try:
        tm = (
            db.query(TeamMember)
            .filter(TeamMember.team_id == team_id, TeamMember.user_id == payload.user_id)
            .first()
        )
        if not tm:
            raise HTTPException(status_code=404, detail="member_not_found")

        db.delete(tm)
        db.commit()

        return {"ok": True, "removed_user_id": payload.user_id}
    finally:
        db.close()
