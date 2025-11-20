from decimal import Decimal
from typing import Optional
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from fastapi import HTTPException

from backend.app.db import SessionLocal
from backend.app.models.credit_transaction import CreditTransaction
from backend.app.models.credit_reservation import CreditReservation
from backend.app.models.user import User

# cost per verification — change as needed
COST_PER_VERIFICATION = Decimal("1.0")

# reservation expiry (seconds)
RESERVATION_TTL_SECONDS = 60 * 60  # 1 hour


def get_balance(db: Session, user_id: int) -> Decimal:
    """
    Compute balance by summing transactions for the user.
    """
    total = db.query(CreditTransaction).with_entities(
        (CreditTransaction.amount).label("amt")
    ).filter(CreditTransaction.user_id == user_id).all()

    # SQLAlchemy returns list of tuples/rows; sum safely
    balance = Decimal("0")
    for row in total:
        val = row[0]
        balance += Decimal(str(val))
    return balance


def add_credits(db: Session, user_id: int, amount: Decimal, type_: str = "topup", reference: Optional[str] = None, metadata: Optional[str] = None) -> CreditTransaction:
    """
    Add a credit transaction (topup or refund).
    """
    # compute new balance
    prev_balance = get_balance(db, user_id)
    new_balance = prev_balance + Decimal(amount)

    tx = CreditTransaction(
        user_id=user_id,
        amount=Decimal(amount),
        balance_after=new_balance,
        type=type_,
        reference=reference,
        metadata=metadata,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def reserve_credits(db: Session, user_id: int, amount: Decimal, job_id: Optional[str] = None, reference: Optional[str] = None) -> CreditReservation:
    """
    Attempt to reserve 'amount' credits for a user.
    Raises HTTPException(402) if insufficient funds.
    """
    balance = get_balance(db, user_id)

    # compute total locked reservations for user
    locked_total = db.query(CreditReservation).with_entities(
        CreditReservation.amount
    ).filter(CreditReservation.user_id == user_id, CreditReservation.locked == True).all()

    locked_sum = Decimal("0")
    for r in locked_total:
        locked_sum += Decimal(str(r[0]))

    available = balance - locked_sum
    if Decimal(amount) > available:
        raise HTTPException(status_code=402, detail="insufficient_credits")

    expires_at = datetime.utcnow() + timedelta(seconds=RESERVATION_TTL_SECONDS)
    reservation = CreditReservation(
        user_id=user_id,
        amount=Decimal(amount),
        job_id=job_id,
        locked=True,
        expires_at=expires_at,
        reference=reference,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


def capture_reservation(db: Session, reservation_id: int, type_: str = "charge", reference: Optional[str] = None, metadata: Optional[str] = None) -> CreditTransaction:
    """
    Convert a reservation into a real charge (transaction).
    This will mark reservation.locked = False and create a negative transaction.
    """
    res = db.get(CreditReservation, reservation_id)
    if not res or not res.locked:
        raise HTTPException(status_code=404, detail="reservation_not_found_or_already_captured")

    # compute balance prior to charge
    balance = get_balance(db, res.user_id)
    new_balance = balance - Decimal(res.amount)

    tx = CreditTransaction(
        user_id=res.user_id,
        amount=Decimal(-res.amount),
        balance_after=new_balance,
        type=type_,
        reference=reference or res.reference,
        metadata=metadata,
    )
    # mark reservation unlocked
    res.locked = False
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def release_reservation(db: Session, reservation_id: int) -> bool:
    """
    Release the reservation (set locked=False) without charging.
    """
    res = db.get(CreditReservation, reservation_id)
    if not res or not res.locked:
        return False
    res.locked = False
    db.commit()
    return True


def cleanup_expired_reservations(db: Session):
    """
    Optionally run periodically: mark expired reservations as unlocked.
    """
    now = datetime.utcnow()
    expired = db.query(CreditReservation).filter(CreditReservation.expires_at < now, CreditReservation.locked == True).all()
    for r in expired:
        r.locked = False
    db.commit()
