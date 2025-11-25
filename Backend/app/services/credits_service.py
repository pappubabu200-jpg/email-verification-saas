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

RESERVATION_TTL = 3600  # 1 hour


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def _dec(x) -> Decimal:
    """Safe Decimal converter."""
    return Decimal(str(x)) if x is not None else Decimal("0")


# ---------------------------------------------------------
# BALANCE
# ---------------------------------------------------------

def get_user_balance(user_id: int) -> Decimal:
    """
    Returns REAL balance from User.credits.
    Fallback: last CreditTransaction.
    """
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(404, "user_not_found")

        # Fast path
        if hasattr(user, "credits"):
            return _dec(user.credits)

        # Fallback — last transaction
        last_tx = (
            db.query(CreditTransaction)
            .filter(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc())
            .first()
        )
        if last_tx:
            return _dec(last_tx.balance_after)

        return Decimal("0")
    finally:
        db.close()


# ---------------------------------------------------------
# ADD CREDITS (TOP-UP / REFUND)
# ---------------------------------------------------------

def add_credits(
    user_id: int,
    amount: Decimal,
    reference: Optional[str] = None,
    metadata: Optional[str] = None,
) -> dict:
    """
    Add credits to user's balance.
    Used by Stripe webhook, admin, refunds.
    """
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(404, "user_not_found")

        amount = _dec(amount)
        balance_before = _dec(user.credits)
        new_balance = balance_before + amount

        user.credits = float(new_balance)

        tx = CreditTransaction(
            user_id=user.id,
            amount=float(amount),
            balance_after=float(new_balance),
            type="credit",
            reference=reference or "",
            metadata=str(metadata or ""),
        )

        db.add(tx)
        db.add(user)
        db.commit()
        db.refresh(tx)

        return {
            "balance_after": float(new_balance),
            "transaction_id": tx.id,
        }

    except Exception as e:
        logger.exception("add_credits failed: %s", e)
        raise HTTPException(500, "credit_error")

    finally:
        db.close()


# ---------------------------------------------------------
# RESERVE CREDITS
# ---------------------------------------------------------

def reserve_and_deduct(
    user_id: int,
    amount: Decimal,
    reference: Optional[str] = None,
    team_id: Optional[int] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    CREDIT RESERVATION (pre-charge):
    - Team billing first
    - If insufficient → fallback to user
    - Creates locked reservation
    """
    amount = _dec(amount)

    # -------------------------------
    # TEAM BILLING PRIORITY
    # -------------------------------
    if team_id:
        try:
            from backend.app.services.team_billing_service import reserve_and_deduct_team
            return reserve_and_deduct_team(team_id, amount, reference=reference, job_id=job_id)

        except HTTPException as e:
            # insufficient in team → fallback to user
            if e.status_code != 402:
                raise

    # -------------------------------
    # USER RESERVATION
    # -------------------------------
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(404, "user_not_found")

        balance = _dec(user.credits)

        # prevent overcommit → subtract locked reservations
        locked_reservations = (
            db.query(CreditReservation)
            .filter(CreditReservation.user_id == user_id, CreditReservation.locked == True)
            .all()
        )

        already_locked = sum((_dec(r.amount) for r in locked_reservations), Decimal("0"))
        available = balance - already_locked

        if amount > available:
            raise HTTPException(402, "insufficient_credits")

        reservation = CreditReservation(
            user_id=user_id,
            amount=float(amount),
            job_id=job_id,
            locked=True,
            expires_at=datetime.utcnow() + timedelta(seconds=RESERVATION_TTL),
            reference=reference or "",
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


# ---------------------------------------------------------
# CAPTURE RESERVATION (FINAL CHARGE)
# ---------------------------------------------------------

def capture_reservation_and_charge(
    db: Session,
    reservation_id: int,
    type_: str = "charge",
    reference: Optional[str] = None,
) -> CreditTransaction:
    """
    Final step:
    Converts reservation → real charge.
    Deducts from balance.
    """
    res = db.query(CreditReservation).get(reservation_id)
    if not res or not res.locked:
        raise HTTPException(404, "reservation_not_found_or_unlocked")

    user = db.query(User).get(res.user_id)
    if not user:
        raise HTTPException(404, "user_not_found")

    amount = _dec(res.amount)
    balance = _dec(user.credits)

    if balance < amount:
        raise HTTPException(402, "insufficient_credits_at_capture")

    new_balance = balance - amount
    user.credits = float(new_balance)

    tx = CreditTransaction(
        user_id=user.id,
        amount=-float(amount),
        balance_after=float(new_balance),
        type=type_,
        reference=reference or res.reference,
    )

    res.locked = False

    db.add(tx)
    db.add(user)
    db.commit()
    db.refresh(tx)
    return tx


# ---------------------------------------------------------
# RESERVATION RELEASE (NO CHARGE)
# ---------------------------------------------------------

def release_reservation(db: Session, reservation_id: int) -> bool:
    """Unlocks reservation without charging."""
    res = db.query(CcreditReservation).get(reservation_id)
    if not res or not res.locked:
        return False

    res.locked = False
    db.commit()
    return True


def release_reservation_by_job(job_id: str) -> int:
    """Unlock all reservations for given job."""
    db = SessionLocal()
    try:
        rows = (
            db.query(CreditReservation)
            .filter(CreditReservation.job_id == job_id, CreditReservation.locked == True)
            .all()
        )
        for r in rows:
            r.locked = False
            db.add(r)

        db.commit()
        return len(rows)
    finally:
        db.close()
