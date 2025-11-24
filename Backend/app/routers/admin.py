# backend/app/routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.services.auth_service import get_current_admin
from backend.app.db import async_session

from backend.app.repositories.user_repository import UserRepository
from backend.app.repositories.team_repository import TeamRepository
from backend.app.repositories.credit_transaction_repository import CreditTransactionRepository

router = APIRouter(prefix="/admin", tags=["admin"])


async def get_db():
    async with async_session() as session:
        yield session


# ---------------------------------------
# List all users
# ---------------------------------------
@router.get("/users")
async def admin_list_users(
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    repo = UserRepository(db)
    return await repo.all()


# ---------------------------------------
# Manually adjust user credits
# ---------------------------------------
@router.post("/adjust-credits")
async def adjust_credits(
    user_id: int,
    amount: float,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    repo = UserRepository(db)
    tx_repo = CreditTransactionRepository(db)

    user = await repo.get(user_id)
    if not user:
        raise HTTPException(404, "User not found")

    new_balance = float(user.credits) + amount

    user.credits = new_balance
    await tx_repo.create({
        "user_id": user.id,
        "amount": amount,
        "balance_after": new_balance,
        "type": "admin_adjust",
        "reference": "admin"
    })

    return {"ok": True, "new_balance": new_balance}


# ---------------------------------------
# Ban a user
# ---------------------------------------
@router.post("/ban/{user_id}")
async def ban_user(
    user_id: int,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(404, "User not found")

    await repo.update(user, {"is_active": False})

    return {"banned": True}


# ---------------------------------------
# Unban
# ---------------------------------------
@router.post("/unban/{user_id}")
async def unban_user(
    user_id: int,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    repo = UserRepository(db)
    user = await repo.get(user_id)

    if not user:
        raise HTTPException(404, "User not found")

    await repo.update(user, {"is_active": True})

    return {"unbanned": True}
