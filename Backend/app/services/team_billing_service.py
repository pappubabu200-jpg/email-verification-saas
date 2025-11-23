# backend/app/services/team_billing_service.py
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_credit_transaction import TeamCreditTransaction
from backend.app.models.credit_reservation import CreditReservation

import logging
logger = logging.getLogger(__name__)


# ---------------------------
# INTERNAL BALANCE HELPERS
# ---------------------------

def _team_balance(db: Session, team_id: int) -> Decimal:
    """
    Compute team balance from the team's `credits` column if present,
    else from latest team transaction.
    """
    team = db.query(Team).get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")

    # Fast path: direct column
    if hasattr(team, "credits"):
        return Decimal(team.credits or 0)

    # Otherwise compute from transactions
    row = (
        db.query(TeamCreditTransaction)
        .filter(TeamCreditTransaction.team_id == team_id)
        .order_by(TeamCreditTransaction.created_at.desc())
        .first()
    )
    return Decimal(row.balance_after) if row else Decimal("0")


def _apply_team_tx(db: Session, team_id: int, amount: Decimal, type_: str, reference=None, metadata=None):
    """
    Create a team credit transaction and update the team's credits.
    """
    team = db.query(Team).get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="team_not_found")

    prev = Decimal(team.credits or 0)
    new = prev + amount
    team.credits = new

    tx = TeamCreditTransaction(
        team_id=team_id,
        amount=amount,
        balance_after=new,
        type=type_,
        reference=reference,
        metadata=metadata,
    )

    db.add(team)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


# ---------------------------
# ADD CREDITS TO TEAM
# ---------------------------

def add_team_credits(team_id: int, amount: Decimal, reference=None):
    """
    Add credits to a team (top-up or refund).
    """
    db = SessionLocal()
    try:
        return _apply_team_tx(db, team_id, amount, type_="credit", reference=reference)
    finally:
        db.close()


# ---------------------------
# RESERVE TEAM CREDITS
# ---------------------------

def reserve_and_deduct_team(team_id: int, amount: Decimal, reference=None, job_id=None):
    """
    Reserve team credits. Creates a CreditReservation row.
    """
    db = SessionLocal()
    try:
        balance = _team_balance(db, team_id)

        if balance < amount:
            raise HTTPException(status_code=402, detail="team_insufficient_credits")

        expires = datetime.utcnow() + timedelta(hours=1)

        res = CreditReservation(
            team_id=team_id,
            amount=amount,
            job_id=job_id,
            locked=True,
            expires_at=expires,
            reference=reference,
        )

        db.add(res)
        db.commit()
        db.refresh(res)

        # DO NOT immediately deduct from team column yet — only after capture
        return {
            "reservation_id": res.id,
            "reserved_amount": float(amount),
            "team_id": team_id,
            "job_id": job_id,
        }

    finally:
        db.close()


# ---------------------------
# CAPTURE (FINAL CHARGE)
# ---------------------------

def capture_reservation_and_charge(reservation_id: int, type_="charge", reference=None):
    """
    Convert reservation into a real debit.
    Deducts credits from team.
    """
    db = SessionLocal()
    try:
        r = db.query(CreditReservation).get(reservation_id)
        if not r or not r.locked:
            raise HTTPException(status_code=404, detail="reservation_not_found")

        team_id = getattr(r, "team_id", None)
        if not team_id:
            raise HTTPException(status_code=400, detail="not_a_team_reservation")

        # mark unlocked BEFORE charging
        r.locked = False
        db.add(r)
        db.commit()

        # debit team
        amount = Decimal(r.amount)
        tx = _apply_team_tx(
            db,
            team_id,
            -amount,
            type_=type_,
            reference=reference or r.reference,
        )

        return {"captured": float(amount), "team_id": team_id, "tx_id": tx.id}

    finally:
        db.close()


# ---------------------------
# RELEASE RESERVATION
# ---------------------------

def release_reservation_by_job(job_id: str):
    """
    Release all reservations for job without charging.
    """
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
        return {"released": len(rows)}
    finally:
        db.close()
# backend/app/services/team_billing_service.py

from decimal import Decimal
from fastapi import HTTPException
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from backend.app.models.credit_transaction import CreditTransaction
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------
# GET TEAM BALANCE
# ----------------------------------------------
def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")

        return Decimal(team.credits or 0)
    finally:
        db.close()


# ----------------------------------------------
# ADD CREDITS TO TEAM
# ----------------------------------------------
def add_team_credits(team_id: int, amount: Decimal, reference: str = None):
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")

        new_balance = Decimal(team.credits) + amount
        team.credits = float(new_balance)

        tx = CreditTransaction(
            user_id=None,
            amount=amount,
            balance_after=new_balance,
            type="team_credit",
            reference=reference or "",
        )
        db.add(team)
        db.add(tx)
        db.commit()
        return {"balance_after": float(new_balance)}
    except Exception as e:
        logger.exception("add_team_credits failed: %s", e)
        raise HTTPException(status_code=500, detail="team_credit_error")
    finally:
        db.close()


# ----------------------------------------------
# TEAM RESERVE + DEDUCT (FIRST PRIORITY)
# ----------------------------------------------
def reserve_and_deduct_team(team_id: int, amount: Decimal, reference: str = None, job_id: str = None):
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")

        balance = Decimal(team.credits or 0)
        if balance < amount:
            raise HTTPException(status_code=402, detail="team_insufficient_credits")

        new_balance = balance - amount
        team.credits = float(new_balance)

        # record as team debit
        tx = CreditTransaction(
            user_id=None,
            amount=-amount,
            balance_after=new_balance,
            type="team_debit",
            reference=reference or "",
            metadata=f"team:{team_id},job:{job_id}",
        )
        db.add(team)
        db.add(tx)
        db.commit()

        return {"team_id": team_id, "balance_after": float(new_balance), "reserved": float(amount)}
    finally:
        db.close()
