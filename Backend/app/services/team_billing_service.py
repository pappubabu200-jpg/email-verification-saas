# backend/app/services/team_billing_service.py

from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_credit_transaction import TeamCreditTransaction
from backend.app.models.credit_reservation import CreditReservation

logger = logging.getLogger(__name__)

RESERVATION_TTL = 3600  # 1 hour


# ---------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------

def _dec(x) -> Decimal:
    return Decimal(str(x or 0))


def _get_team(db: Session, team_id: int) -> Team:
    team = db.query(Team).get(team_id)
    if not team:
        raise HTTPException(404, "team_not_found")
    return team


def _team_balance(db: Session, team_id: int) -> Decimal:
    team = _get_team(db, team_id)
    return _dec(team.credits)


def _apply_team_tx(
    db: Session,
    team_id: int,
    amount: Decimal,
    type_: str,
    reference: Optional[str] = None,
    metadata: Optional[str] = None,
) -> TeamCreditTransaction:
    """
    Apply credit/debit to team and save transaction.
    """
    team = _get_team(db, team_id)

    before = _dec(team.credits)
    after = before + amount

    team.credits = float(after)

    tx = TeamCreditTransaction(
        team_id=team_id,
        amount=float(amount),
        balance_after=float(after),
        type=type_,
        reference=reference,
        metadata=metadata,
    )

    db.add(team)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


# ---------------------------------------------------------
# Public APIs
# ---------------------------------------------------------

def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        return _team_balance(db, team_id)
    finally:
        db.close()


def add_team_credits(team_id: int, amount: Decimal, reference: Optional[str] = None):
    """
    Top-up / refund team credits.
    """
    amount = _dec(amount)
    db = SessionLocal()
    try:
        tx = _apply_team_tx(db, team_id, amount, type_="credit", reference=reference)
        return {"balance_after": tx.balance_after, "tx_id": tx.id}
    finally:
        db.close()


# ---------------------------------------------------------
# RESERVE TEAM CREDITS (used by credits_service)
# ---------------------------------------------------------

def reserve_and_deduct_team(
    team_id: int,
    amount: Decimal,
    reference: Optional[str] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    Reserve team credits without deducting immediately.
    Real deduction happens during capture.
    """
    amount = _dec(amount)
    db = SessionLocal()
    try:
        balance = _team_balance(db, team_id)

        if balance < amount:
            raise HTTPException(402, "team_insufficient_credits")

        expires = datetime.utcnow() + timedelta(seconds=RESERVATION_TTL)

        reservation = CreditReservation(
            user_id=None,
            team_id=team_id,
            amount=float(amount),
            job_id=job_id,
            locked=True,
            expires_at=expires,
            reference=reference,
        )

        db.add(reservation)
        db.commit()
        db.refresh(reservation)

        return {
            "reservation_id": reservation.id,
            "reserved_amount": float(amount),
            "team_id": team_id,
            "job_id": job_id,
        }

    finally:
        db.close()


# ---------------------------------------------------------
# CAPTURE (FINAL CHARGE)
# ---------------------------------------------------------

def capture_reservation_and_charge(
    reservation_id: int,
    type_: str = "debit",
    reference: Optional[str] = None,
):
    """
    Deduct reserved credits from the team.
    """

    db = SessionLocal()
    try:
        r = db.query(CreditReservation).get(reservation_id)
        if not r or not r.locked:
            raise HTTPException(404, "reservation_not_found")

        if not r.team_id:
            raise HTTPException(400, "not_a_team_reservation")

        team_id = r.team_id
        amount = _dec(r.amount)

        # mark unlocked BEFORE charging
        r.locked = False
        db.add(r)
        db.commit()

        tx = _apply_team_tx(
            db,
            team_id,
            -amount,
            type_=type_,
            reference=reference or r.reference,
        )

        return {
            "captured": float(amount),
            "team_id": team_id,
            "tx_id": tx.id,
        }

    finally:
        db.close()


# ---------------------------------------------------------
# RELEASE (NO CHARGE)
# ---------------------------------------------------------

def release_reservation_by_job(job_id: str):
    """
    Unlock all reservations for the job, without charging.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(CreditReservation)
            .filter(CreditReservation.job_id == job_id,
                    CreditReservation.locked == True)
            .all()
        )
        for r in rows:
            r.locked = False
            db.add(r)

        db.commit()
        return {"released": len(rows)}
    finally:
        db.close()
