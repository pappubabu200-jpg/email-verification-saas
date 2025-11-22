from decimal import Decimal
from backend.app.db import SessionLocal
from backend.app.models.team_balance import TeamBalance
from backend.app.models.team_credit_transaction import TeamCreditTransaction
from backend.app.models.team import Team
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def _to_decimal(v) -> Decimal:
    return Decimal(str(v or 0))

def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        tb = db.query(TeamBalance).filter(TeamBalance.team_id == team_id).first()
        if not tb:
            return Decimal("0")
        return _to_decimal(tb.balance)
    finally:
        db.close()

def ensure_team_balance_row(team_id: int):
    db = SessionLocal()
    try:
        tb = db.query(TeamBalance).filter(TeamBalance.team_id == team_id).first()
        if not tb:
            tb = TeamBalance(team_id=team_id, balance=0)
            db.add(tb); db.commit(); db.refresh(tb)
        return tb
    finally:
        db.close()

def add_team_credits(team_id: int, amount: Decimal, reference: str = None, metadata: str = None) -> dict:
    db = SessionLocal()
    try:
        tb = db.query(TeamBalance).with_for_update().filter(TeamBalance.team_id == team_id).first()
        if not tb:
            tb = TeamBalance(team_id=team_id, balance=0)
            db.add(tb); db.commit(); db.refresh(tb)
        prev = _to_decimal(tb.balance)
        tb.balance = prev + _to_decimal(amount)
        tr = TeamCreditTransaction(team_id=team_id, amount=Decimal(amount), balance_after=tb.balance, type="topup", reference=reference or "", metadata=metadata)
        db.add(tr)
        db.add(tb)
        db.commit()
        db.refresh(tr)
        return {"balance_after": float(tb.balance), "transaction_id": tr.id}
    except Exception as e:
        logger.exception("add_team_credits failed: %s", e)
        raise HTTPException(status_code=500, detail="team_credit_error")
    finally:
        db.close()

def reserve_and_deduct_team(team_id: int, amount: Decimal, reference: str = None) -> dict:
    """
    Atomically deduct from team pool. Raises 402 if insufficient.
    """
    db = SessionLocal()
    try:
        tb = db.query(TeamBalance).with_for_update().filter(TeamBalance.team_id == team_id).first()
        if not tb:
            raise HTTPException(status_code=402, detail="team_insufficient")
        prev = _to_decimal(tb.balance)
        if prev < _to_decimal(amount):
            raise HTTPException(status_code=402, detail="team_insufficient")
        tb.balance = prev - _to_decimal(amount)
        tr = TeamCreditTransaction(team_id=team_id, amount=-Decimal(amount), balance_after=tb.balance, type="debit", reference=reference or "")
        db.add(tr)
        db.add(tb)
        db.commit()
        db.refresh(tr)
        return {"balance_after": float(tb.balance), "transaction_id": tr.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("reserve_and_deduct_team failed: %s", e)
        raise HTTPException(status_code=500, detail="team_credit_error")
    finally:
        db.close()

def transfer_team_to_user(team_id: int, user_id: int, amount: Decimal, reference: str = None) -> dict:
    """
    Transfer credits out of team and return metadata; actual user credit addition should be done via credits_service.add_credits
    """
    db = SessionLocal()
    try:
        tb = db.query(TeamBalance).with_for_update().filter(TeamBalance.team_id == team_id).first()
        if not tb:
            raise HTTPException(status_code=402, detail="team_insufficient")
        prev = _to_decimal(tb.balance)
        if prev < _to_decimal(amount):
            raise HTTPException(status_code=402, detail="team_insufficient")
        tb.balance = prev - _to_decimal(amount)
        tr = TeamCreditTransaction(team_id=team_id, amount=-Decimal(amount), balance_after=tb.balance, type="transfer_out", reference=reference or f"transfer_to_user:{user_id}")
        db.add(tr); db.add(tb); db.commit(); db.refresh(tr)
        return {"balance_after": float(tb.balance), "transaction_id": tr.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("transfer_team_to_user failed: %s", e)
        raise HTTPException(status_code=500, detail="team_credit_error")
    finally:
        db.close()

def list_team_transactions(team_id: int, limit: int = 50):
    db = SessionLocal()
    try:
        rows = db.query(TeamCreditTransaction).filter(TeamCreditTransaction.team_id == team_id).order_by(TeamCreditTransaction.created_at.desc()).limit(limit).all()
        return rows
    finally:
        db.close()


# backend/app/services/team_billing_service.py
from decimal import Decimal
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.credit_transaction import CreditTransaction
from backend.app.models.credit_reservation import CreditReservation
from fastapi import HTTPException
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

RESERVATION_TTL_SECONDS = 60 * 60  # 1 hour

def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        return Decimal(t.credits or 0)
    finally:
        db.close()

def add_team_credits(team_id: int, amount: Decimal, reference: str = None) -> dict:
    """
    Top-up team pool by writing a transaction row and updating Team.credits atomically.
    """
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        prev = Decimal(t.credits or 0)
        new = prev + Decimal(amount)
        t.credits = float(new)
        db.add(t)
        tx = CreditTransaction(user_id=None, amount=float(amount), balance_after=new, type="team_credit", reference=reference or f"team_topup:{team_id}")
        # store team id in reference or metadata (we reuse CreditTransaction.user_id == None for team tx)
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return {"balance_after": float(new), "transaction_id": tx.id}
    except Exception as e:
        logger.exception("add_team_credits failed: %s", e)
        raise HTTPException(status_code=500, detail="team_credit_error")
    finally:
        db.close()

def reserve_and_deduct_team(team_id: int, amount: Decimal, job_id: str = None, reference: str = None) -> dict:
    """
    Reserve and charge from the team pool atomically.
    Returns transaction dict similar to reserve_and_deduct user.
    Raises HTTPException(402) if insufficient.
    """
    db = SessionLocal()
    try:
        t = db.query(Team).with_for_update().get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        balance = Decimal(t.credits or 0)
        if balance < amount:
            raise HTTPException(status_code=402, detail="team_insufficient_credits")
        new_balance = balance - Decimal(amount)
        t.credits = float(new_balance)
        db.add(t)
        tx = CreditTransaction(user_id=None, amount=float(-amount), balance_after=new_balance, type="team_debit", reference=reference or f"team_charge:{team_id}")
        db.add(tx)
        db.commit()
        db.refresh(tx)
        return {"balance_after": float(new_balance), "transaction_id": tx.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("reserve_and_deduct_team failed: %s", e)
        raise HTTPException(status_code=500, detail="team_charge_error")
    finally:
        db.close()

def refund_to_team(team_id: int, amount: Decimal, reference: str = None) -> dict:
    """
    Refund amount back to team credits (adds a positive tx).
    """
    return add_team_credits(team_id, amount, reference=reference)


# backend/app/services/team_billing_service.py

from decimal import Decimal
from fastapi import HTTPException
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.credit_transaction import CreditTransaction
import logging

logger = logging.getLogger(__name__)

def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")
        return Decimal(team.credits or 0)
    finally:
        db.close()

def reserve_and_deduct_team(team_id: int, amount: Decimal, reference: str = None):
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")

        bal = Decimal(team.credits or 0)
        if bal < amount:
            raise HTTPException(status_code=402, detail="team_insufficient_credits")

        new_balance = bal - amount
        team.credits = float(new_balance)

        tx = CreditTransaction(
            team_id=team_id,
            amount=-amount,
            balance_after=new_balance,
            type="debit",
            reference=reference,
        )
        db.add(tx)
        db.add(team)
        db.commit()
        return {"balance_after": float(new_balance), "transaction_id": tx.id}
    finally:
        db.close()

def add_team_credits(team_id: int, amount: Decimal, reference: str = None):
    db = SessionLocal()
    try:
        team = db.query(Team).get(team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_not_found")

        new_balance = Decimal(team.credits or 0) + amount
        team.credits = float(new_balance)

        tx = CreditTransaction(
            team_id=team_id,
            amount=amount,
            balance_after=new_balance,
            type="credit",
            reference=reference,
        )
        db.add(tx)
        db.add(team)
        db.commit()
        return {"balance_after": float(new_balance), "transaction_id": tx.id}
    finally:
        db.close()

from decimal import Decimal
from datetime import datetime, timedelta
from backend.app.db import SessionLocal
from backend.app.models.team import Team
from backend.app.models.credit_reservation import CreditReservation
from backend.app.models.credit_transaction import CreditTransaction
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)
RESERVATION_TTL_SECONDS = 60 * 60  # 1 hour

def get_team_balance(team_id: int) -> Decimal:
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        return Decimal(t.credits or 0)
    finally:
        db.close()

def add_team_credits(team_id: int, amount: Decimal, reference: str = None) -> dict:
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        new_balance = Decimal(t.credits or 0) + Decimal(amount)
        t.credits = new_balance
        tx = CreditTransaction(user_id=None, amount=float(amount), balance_after=float(new_balance), type="team_topup", reference=reference or f"team_topup:{team_id}")
        # For team transactions we store user_id=None; admin can trace by reference
        db.add(tx); db.add(t); db.commit(); db.refresh(tx)
        return {"balance_after": float(new_balance), "transaction_id": tx.id}
    finally:
        db.close()

def reserve_and_deduct_team(team_id: int, amount: Decimal, reference: str = None, job_id: str = None) -> dict:
    """
    Reserve from team pool (create CreditReservation.team_id)
    """
    db = SessionLocal()
    try:
        t = db.query(Team).get(team_id)
        if not t:
            raise HTTPException(status_code=404, detail="team_not_found")
        balance = Decimal(t.credits or 0)
        # compute locked reservations for team
        locked_rows = db.query(CreditReservation).filter(CreditReservation.team_id == team_id, CreditReservation.locked == True).all()
        locked_sum = Decimal("0")
        for r in locked_rows:
            locked_sum += Decimal(r.amount)
        available = balance - locked_sum
        if Decimal(amount) > available:
            raise HTTPException(status_code=402, detail="team_insufficient_credits")
        expires_at = datetime.utcnow() + timedelta(seconds=RESERVATION_TTL_SECONDS)
        res = CreditReservation(team_id=team_id, user_id=None, amount=amount, job_id=job_id, locked=True, expires_at=expires_at, reference=reference)
        db.add(res); db.commit(); db.refresh(res)
        return {"reservation_id": res.id, "reserved_amount": float(amount), "team_id": team_id, "job_id": job_id}
    finally:
        db.close()

def capture_team_reservation(reservation_id: int, type_: str = "team_charge", reference: str = None) -> dict:
    """
    Capture reservation and deduct from team. Creates a CreditTransaction for admin trace.
    """
    db = SessionLocal()
    try:
        res = db.query(CreditReservation).get(reservation_id)
        if not res or not res.locked:
            raise HTTPException(status_code=404, detail="reservation_missing_or_unlocked")
        if not res.team_id:
            raise HTTPException(status_code=400, detail="not_team_reservation")
        team = db.query(Team).get(res.team_id)
        if not team:
            raise HTTPException(status_code=404, detail="team_missing")
        amt = Decimal(res.amount)
        team.credits = Decimal(team.credits or 0) - amt
        res.locked = False
        tx = CreditTransaction(user_id=None, amount=-float(amt), balance_after=float(team.credits), type=type_, reference=reference or res.reference)
        db.add(tx); db.add(team); db.add(res); db.commit(); db.refresh(tx)
        return {"transaction_id": tx.id, "balance_after": float(team.credits)}
    finally:
        db.close()
