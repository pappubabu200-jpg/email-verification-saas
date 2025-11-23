# backend/app/services/credits_service.py
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.models.credit_transaction import CreditTransaction
from backend.app.models.credit_reservation import CreditReservation

logger = logging.getLogger(__name__)

RESERVATION_TTL = 3600   # 1 hour


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _dec(x) -> Decimal:
    return Decimal(str(x))


def get_user_balance(user_id: int) -> Decimal:
    """
    Returns current balance from User.credits if exists.
    Otherwise computes from CreditTransaction table.
    """
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(404, "user_not_found")

        # Fast path – direct numeric column
        if hasattr(user, "credits"):
            return Decimal(user.credits or 0)

        # Fallback – sum transactions
        rows = db.query(CreditTransaction.amount).filter(
            CreditTransaction.user_id == user_id
        ).all()
        total = Decimal("0")
        for r in rows:
            total += Decimal(str(r[0]))
        return total

    finally:
        db.close()


# --------------------------------------------------
# RESERVATION FLOW (NEW, CORRECT)
# --------------------------------------------------

def reserve_and_deduct(
    user_id: int,
    amount: Decimal,
    reference: Optional[str] = None,
    team_id: Optional[int] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    Reserve credits. Does NOT charge immediately.
    - If team_id provided → use team pool first.
    - If insufficient team credits → fall back to user.
    - Creates reservation row (locked=True).
    - Final charge/refund happens later by capture_reservation or refund.
    """

    amount = _dec(amount)

    # TEAM FIRST
    if team_id:
        from backend.app.services.team_billing_service import reserve_and_deduct_team

        try:
            return reserve_and_deduct_team(
                team_id, amount, reference=reference, job_id=job_id
            )
        except HTTPException as e:
            # If not insufficient → propagate error
            if e.status_code != 402:
                raise
            # else fall back to user

    # USER RESERVATION
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(404, "user_not_found")

        balance = _dec(user.credits or 0)
        if balance < amount:
            raise HTTPException(402, "insufficient_credits")

        expires_at = datetime.utcnow() + timedelta(seconds=RESERVATION_TTL)

        reservation = CreditReservation(
            user_id=user_id,
            amount=amount,
            job_id=job_id,
            locked=True,
            expires_at=expires_at,
            reference=reference,
        )

        db.add(reservation)
        db.commit()
        db.refresh(reservation)

        return {
            "reservation_id": reservation.id,
            "reserved_amount": float(amount),
            "job_id": job_id,
        }

    finally:
        db.close()


def capture_reservation_and_charge(
    db: Session,
    reservation_id: int,
    type_: str = "charge",
    reference: Optional[str] = None,
) -> CreditTransaction:
    """
    Convert reservation to a charge.
    Deducts from user immediately.
    """
    res = db.query(CreditReservation).get(reservation_id)
    if not res or not res.locked:
        raise HTTPException(404, "reservation_not_found_or_unlocked")

    user = db.query(User).get(res.user_id)
    if not user:
        raise HTTPException(404, "user_not_found")

    amount = _dec(res.amount)
    balance = _dec(user.credits or 0)

    if balance < amount:
        # Should not happen normally
        raise HTTPException(402, "insufficient_credits_at_capture")

    # Deduct
    new_balance = balance - amount
    user.credits = float(new_balance)

    tx = CreditTransaction(
        user_id=user.id,
        amount=-amount,
        balance_after=new_balance,
        type=type_,
        reference=reference or res.reference,
    )

    # Mark reservation unlocked
    res.locked = False

    db.add(tx)
    db.add(user)
    db.commit()
    db.refresh(tx)

    return tx


def release_reservation(db: Session, reservation_id: int) -> bool:
    """
    Releases reservation without charging.
    """
    res = db.query(CreditReservation).get(reservation_id)
    if not res or not res.locked:
        return False

    res.locked = False
    db.commit()
    return True


def release_reservation_by_job(job_id: str) -> int:
    """
    Releases ALL reservations with job_id
    """
    db = SessionLocal()
    try:
        rows = db.query(CreditReservation).filter(
            CreditReservation.job_id == job_id,
            CreditReservation.locked == True,
        ).all()

        for r in rows:
            r.locked = False

        db.commit()
        return len(rows)
    finally:
        db.close()


# --------------------------------------------------
# Direct credit addition (top-ups)
# --------------------------------------------------

def add_credits(
    user_id: int,
    amount: Decimal,
    reference: Optional[str] = None,
) -> dict:
    """
    Add credits to user balance (top-up or refund)
    """
    amount = _dec(amount)
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(404, "user_not_found")

        new_balance = _dec(user.credits or 0) + amount
        user.credits = float(new_balance)

        tx = CreditTransaction(
            user_id=user.id,
            amount=float(amount),
            balance_after=float(new_balance),
            type="credit",
            reference=reference or "",
        )

        db.add(tx)
        db.commit()
        db.refresh(tx)

        return {
            "balance_after": float(new_balance),
            "transaction_id": tx.id,
        }

    finally:
        db.close()
