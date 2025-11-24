
# backend/app/routers/team.py

from fastapi import (
    APIRouter, Depends, HTTPException
)
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.services.auth_service import get_current_user
from backend.app.repositories.team_repository import TeamRepository
from backend.app.repositories.team_member_repository import TeamMemberRepository
from backend.app.repositories.team_balance_repository import TeamBalanceRepository
from backend.app.repositories.team_credit_transaction_repository import TeamCreditTransactionRepository
from backend.app.repositories.audit_log_repository import AuditLogRepository
from backend.app.schemas.team import TeamCreate, TeamResponse
from backend.app.schemas.team_member import TeamMemberResponse

router = APIRouter(prefix="/team", tags=["team-management"])


# ---------------------------------------
# DB dependency
# ---------------------------------------
async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------
# Helper: require team owner
# ---------------------------------------
async def require_team_owner(team_id: int, user, db):
    team_repo = TeamRepository(db)
    team = await team_repo.get(team_id)

    if not team:
        raise HTTPException(404, "Team not found")

    if team.owner_id != user.id:
        raise HTTPException(403, "Only team owner can perform this action")

    return team


# ---------------------------------------------------------
# POST /team/create  → Create a Team
# ---------------------------------------------------------
@router.post("/create", response_model=TeamResponse)
async def create_team(
    payload: TeamCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    team_repo = TeamRepository(db)

    # Create team
    team = await team_repo.create({
        "name": payload.name,
        "owner_id": current_user.id
    })

    # Add owner as TeamMember (role=owner)
    member_repo = TeamMemberRepository(db)
    await member_repo.create({
        "team_id": team.id,
        "user_id": current_user.id,
        "role": "owner",
    })

    # Create balance record
    balance_repo = TeamBalanceRepository(db)
    await balance_repo.create({
        "team_id": team.id,
        "balance": 0
    })

    return TeamResponse.from_orm(team)


# ---------------------------------------------------------
# GET /team/list  → List teams user belongs to
# ---------------------------------------------------------
@router.get("/list", response_model=list[TeamResponse])
async def list_teams(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    member_repo = TeamMemberRepository(db)
    teams = await member_repo.get_user_teams(current_user.id)
    return [TeamResponse.from_orm(t) for t in teams]


# ---------------------------------------------------------
# GET /team/{team_id} → Team details
# ---------------------------------------------------------
@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    team_repo = TeamRepository(db)
    team = await team_repo.get(team_id)

    if not team:
        raise HTTPException(404, "Team not found")

    return TeamResponse.from_orm(team)


# ---------------------------------------------------------
# POST /team/{team_id}/add-member
# ---------------------------------------------------------
@router.post("/{team_id}/add-member", response_model=TeamMemberResponse)
async def add_team_member(
    team_id: int,
    user_id: int,
    role: str = "member",
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Check owner
    await require_team_owner(team_id, current_user, db)

    # Add member
    member_repo = TeamMemberRepository(db)

    # Prevent duplicate
    existing = await member_repo.get_member(team_id, user_id)
    if existing:
        raise HTTPException(400, "User already in team")

    member = await member_repo.create({
        "team_id": team_id,
        "user_id": user_id,
        "role": role
    })

    # Log audit
    audit_repo = AuditLogRepository(db)
    await audit_repo.create({
        "user_id": current_user.id,
        "team_id": team_id,
        "event_type": "team_add_member",
        "message": f"Added user {user_id} to team {team_id}"
    })

    return TeamMemberResponse.from_orm(member)


# ---------------------------------------------------------
# POST /team/{team_id}/update-role
# ---------------------------------------------------------
@router.post("/{team_id}/update-role")
async def update_member_role(
    team_id: int,
    user_id: int,
    role: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await require_team_owner(team_id, current_user, db)

    member_repo = TeamMemberRepository(db)
    member = await member_repo.get_member(team_id, user_id)

    if not member:
        raise HTTPException(404, "Member not found")

    await member_repo.update(member, {"role": role})

    return {"updated": True, "role": role}


# ---------------------------------------------------------
# DELETE /team/{team_id}/remove/{user_id}
# ---------------------------------------------------------
@router.delete("/{team_id}/remove/{user_id}")
async def remove_member(
    team_id: int,
    user_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await require_team_owner(team_id, current_user, db)

    member_repo = TeamMemberRepository(db)
    member = await member_repo.get_member(team_id, user_id)

    if not member:
        raise HTTPException(404, "Member not found")

    await member_repo.delete(member)
    return {"removed": True}


# ---------------------------------------------------------
# POST /team/{team_id}/transfer-credits
# ---------------------------------------------------------
@router.post("/{team_id}/transfer-credits")
async def transfer_credits(
    team_id: int,
    direction: str,  # "to_team" or "to_user"
    amount: float,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Move credits between:
       → user's personal balance
       → team's balance
    """

    team = await require_team_owner(team_id, current_user, db)

    balance_repo = TeamBalanceRepository(db)
    team_balance = await balance_repo.get_by_team_id(team_id)

    user_balance = current_user.credits

    tx_repo = TeamCreditTransactionRepository(db)

    if amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    # ------------------------------------
    # Transfer TO TEAM
    # ------------------------------------
    if direction == "to_team":
        if user_balance < amount:
            raise HTTPException(400, "Insufficient user credits")

        # Subtract from user
        current_user.credits = user_balance - amount

        # Add to team
        team_balance.balance += amount

        # Log transaction
        await tx_repo.create({
            "team_id": team_id,
            "amount": amount,
            "balance_after": team_balance.balance,
            "type": "transfer_in",
            "reference": f"user_{current_user.id}"
        })

    # ------------------------------------
    # Transfer TO USER
    # ------------------------------------
    elif direction == "to_user":
        if team_balance.balance < amount:
            raise HTTPException(400, "Team does not have enough credits")

        # Add to user
        current_user.credits = user_balance + amount

        # Subtract from team
        team_balance.balance -= amount

        # Log transaction
        await tx_repo.create({
            "team_id": team_id,
            "amount": -amount,
            "balance_after": team_balance.balance,
            "type": "transfer_out",
            "reference": f"user_{current_user.id}"
        })

    else:
        raise HTTPException(400, "Direction must be 'to_team' or 'to_user'")

    return {"success": True}


# ---------------------------------------------------------
# GET /team/{team_id}/members
# ---------------------------------------------------------
@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def team_members(
    team_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    member_repo = TeamMemberRepository(db)
    members = await member_repo.get_team_members(team_id)
    return [TeamMemberResponse.from_orm(m) for m in members]


# ---------------------------------------------------------
# GET /team/{team_id}/activity
# ---------------------------------------------------------
@router.get("/{team_id}/activity")
async def team_activity(
    team_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    audit_repo = AuditLogRepository(db)
    logs = await audit_repo.get_team_logs(team_id)
    return logs


# ---------------------------------------------------------
# POST /team/{team_id}/leave
# ---------------------------------------------------------
@router.post("/{team_id}/leave")
async def leave_team(
    team_id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    repo = TeamMemberRepository(db)
    member = await repo.get_member(team_id, current_user.id)

    if not member:
        raise HTTPException(404, "Not a team member")

    await repo.delete(member)

    return {"left_team": True}
