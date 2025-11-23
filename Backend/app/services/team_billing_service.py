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

# backend/app/services/team_billing_service.py
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from backend.app.models.team_transaction import TeamTransaction
from backend.app.models.credit_reservation import CreditReservation

logger = logging.getLogger(__name__)
RESERVATION_TTL = 3600  # seconds (1 hour)

def _dec(x) -> Decimal:
    return Decimal(str(x))

def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(404, "team_not_found")
        return _dec(t.credits or 0)
    finally:
        db.close()

def add_team_credits(team_id: int, amount: Decimal, reference: Optional[str] = None) -> dict:
    amount = _dec(amount)
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(404, "team_not_found")
        new_bal = _dec(t.credits or 0) + amount
        t.credits = float(new_bal)
        tr = TeamTransaction(team_id=team_id, amount=float(amount), balance_after=float(new_bal), type="topup", reference=reference or "")
        db.add(tr); db.add(t); db.commit(); db.refresh(tr)
        return {"balance_after": float(new_bal), "transaction_id": tr.id}
    finally:
        db.close()

def reserve_and_deduct_team(team_id: int, amount: Decimal, reference: Optional[str] = None, job_id: Optional[str] = None) -> dict:
    """
    Create a reservation that will be captured later against the team pool.
    Reservation uses CreditReservation table; reference tagged with team id "team:{team_id}".
    """
    amount = _dec(amount)
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(404, "team_not_found")
        balance = _dec(t.credits or 0)
        if balance < amount:
            raise HTTPException(402, "insufficient_team_credits")
        expires_at = datetime.utcnow() + timedelta(seconds=RESERVATION_TTL)
        reservation = CreditReservation(
            user_id=None,
            amount=float(amount),
            job_id=job_id,
            locked=True,
            expires_at=expires_at,
            reference=reference or f"team:{team_id}"
        )
        db.add(reservation)
        db.commit(); db.refresh(reservation)
        return {"reservation_id": reservation.id, "reserved_amount": float(amount), "job_id": job_id}
    finally:
        db.close()

def capture_team_reservation_and_charge(db: Session, reservation_id: int, team_id: int, type_: str = "charge", reference: Optional[str] = None):
    res = db.query(CreditReservation).get(reservation_id)
    if not res or not res.locked:
        raise HTTPException(404, "reservation_not_found_or_unlocked")
    t = db.query(Team).get(team_id)
    if not t:
        raise HTTPException(404, "team_not_found")
    amt = _dec(res.amount)
    bal = _dec(t.credits or 0)
    if bal < amt:
        raise HTTPException(402, "team_insufficient_at_capture")
    new_bal = bal - amt
    t.credits = float(new_bal)
    tr = TeamTransaction(team_id=team_id, amount=-float(amt), balance_after=float(new_bal), type=type_, reference=reference or res.reference)
    res.locked = False
    db.add(t); db.add(tr); db.add(res); db.commit()
    return tr

def release_team_reservation(db: Session, reservation_id: int):
    res = db.query(CreditReservation).get(reservation_id)
    if not res or not res.locked:
        return False
    res.locked = False
    db.commit()
    return True

# membership helpers
def is_user_member_of_team(user_id: int, team_id: int) -> bool:
    db = SessionLocal()
    try:
        m = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id, TeamMember.active == True).first()
        return bool(m)
    finally:
        db.close()

def add_team_member(team_id: int, user_id: int, role: str = "member", can_billing: bool = False) -> dict:
    db = SessionLocal()
    try:
        tm = TeamMember(team_id=team_id, user_id=user_id, role=role, can_billing=can_billing)
        db.add(tm); db.commit(); db.refresh(tm)
        return {"ok": True, "team_member_id": tm.id}
    finally:
        db.close()

def remove_team_member(team_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        m = db.query(TeamMember).filter(TeamMember.team_id==team_id, TeamMember.user_id==user_id).first()
        if not m:
            return False
        m.active = False
        db.add(m); db.commit()
        return True
    finally:
        db.close()


# backend/app/services/team_billing_service.py
from decimal import Decimal
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from backend.app.models.credit_transaction import CreditTransaction
from backend.app.models.user import User
from backend.app.models.credit_reservation import CreditReservation
from fastapi import HTTPException
from datetime import datetime, timedelta

RESERVATION_TTL_SECONDS = 60 * 60

def is_user_member_of_team(db, user_id: int, team_id: int) -> bool:
    m = db.query(TeamMember).filter(TeamMember.user_id == user_id, TeamMember.team_id == team_id, TeamMember.active == True).first()
    return bool(m)

def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        return Decimal(t.credits or 0)
    finally:
        db.close()

def add_team_credits(team_id: int, amount: Decimal, reference: str = None):
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        t.credits = int((t.credits or 0) + int(amount))
        # Record as credit transaction (user_id set to team owner for traceability)
        tx = CreditTransaction(user_id=t.owner_id, amount=float(amount), balance_after=float(t.credits), type="team_credit", reference=reference or "")
        db.add(tx)
        db.add(t)
        db.commit()
        db.refresh(tx)
        return {"balance_after": t.credits, "tx_id": tx.id}
    finally:
        db.close()

def reserve_and_deduct_team(team_id: int, amount: Decimal, reference: str = None, job_id: str = None):
    """
    Reserve credits from team pool (create CreditReservation with user_id = owner_id).
    """
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        if (t.credits or 0) < int(amount):
            raise HTTPException(status_code=402, detail="insufficient_team_credits")
        # create reservation record with user_id as team.owner_id and reference marking team
        expires_at = datetime.utcnow() + timedelta(seconds=RESERVATION_TTL_SECONDS)
        res = CreditReservation(user_id=t.owner_id, amount=int(amount), job_id=job_id, locked=True, expires_at=expires_at, reference=f"team:{team_id}:{reference or ''}")
        db.add(res)
        # deduct team credits immediately (we keep team.credits adjusted upon capture to avoid double spending)
        t.credits = int((t.credits or 0) - int(amount))
        db.add(t)
        db.commit()
        db.refresh(res)
        return {"reservation_id": res.id, "reserved_amount": int(amount), "team_balance_after": t.credits}
    finally:
        db.close()

def capture_reservation_and_charge_team(reservation_id: int, type_: str = "team_charge", reference: str = None):
    db = SessionLocal()
    try:
        from backend.app.models.credit_reservation import CreditReservation
        res = db.query(CreditReservation).get(reservation_id)
        if not res:
            raise HTTPException(status_code=404, detail="reservation_not_found")
        if not res.locked:
            raise HTTPException(status_code=400, detail="reservation_not_locked")
        # create transaction for owner and mark unlocked
        owner_id = res.user_id
        balance = db.query(CreditTransaction).filter(CreditTransaction.user_id==owner_id).order_by(CreditTransaction.created_at.desc()).limit(1).all()
        current = Decimal(balance[0].balance_after) if balance else Decimal("0")
        new_balance = current - Decimal(res.amount)
        tx = CreditTransaction(user_id=owner_id, amount=-res.amount, balance_after=new_balance, type=type_, reference=reference or "")
        res.locked = False
        db.add(tx)
        db.add(res)
        db.commit()
        db.refresh(tx)
        return {"tx_id": tx.id, "balance_after": float(new_balance)}
    finally:
        db.close()




