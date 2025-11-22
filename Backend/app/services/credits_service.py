from datetime import datetime, timedelta
from decimal import Decimal
from backend.app.models.credit_reservation import CreditReservation
from backend.app.models.user import User
from backend.app.db import SessionLocal
from fastapi import HTTPException
from decimal import Decimal
from backend.app.db import SessionLocal
from backend.app.models.user import User
from backend.app.models.credit_transaction import CreditTransaction
from backend.app.services.team_billing_service import (
    get_team_balance, reserve_and_deduct_team, add_team_credits as team_add_credits
)
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def get_user_balance(user_id: int) -> Decimal:
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        if hasattr(user, "credits"):
            return Decimal(user.credits or 0)
        rows = db.query(CreditTransaction).filter(CreditTransaction.user_id==user_id).order_by(CreditTransaction.created_at.desc()).limit(1).all()
        if rows:
            return Decimal(rows[0].balance_after)
        return Decimal(0)
    finally:
        db.close()

def add_credits(user_id: int, amount: Decimal, reference: str=None) -> dict:
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        balance = Decimal(getattr(user, "credits", 0) or 0)
        new_balance = balance + amount
        if hasattr(user, "credits"):
            user.credits = float(new_balance)
            db.add(user)
        tr = CreditTransaction(user_id=user_id, amount=float(amount), balance_after=float(new_balance), type="credit", reference=reference or "")
        db.add(tr)
        db.commit()
        db.refresh(tr)
        return {"balance_after": float(new_balance), "transaction_id": tr.id}
    except Exception as e:
        logger.exception("add_credits failed: %s", e)
        raise HTTPException(status_code=500, detail="credit_error")
    finally:
        db.close()

def reserve_and_deduct(user_id: int, amount: Decimal, reference: str = None, team_id: int = None, job_id: str = None) -> dict:
    """
    Reserve credits for a user or team.
    - If team_id provided -> deduct from team pool first.
    - Otherwise deduct from user balance.
    - Creates a CreditReservation row with job_id attached.
    """

    # 1) If TEAM billing enabled → try team first
    if team_id:
        from backend.app.services.team_billing_service import reserve_and_deduct_team
        try:
            return reserve_and_deduct_team(team_id, amount, reference=reference, job_id=job_id)
        except HTTPException as e:
            if e.status_code != 402:
                raise
            # team insufficient → fallthrough to user personal credits

    # 2) Deduct from USER
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")

        balance = Decimal(getattr(user, "credits", 0) or 0)

        if balance < amount:
            raise HTTPException(status_code=402, detail="insufficient_credits")

        # Lock reservation
        expires_at = datetime.utcnow() + timedelta(hours=1)

        reservation = CreditReservation(
            user_id=user_id,
            amount=amount,
            job_id=job_id,       # 🔥 KEY: link reservation to job
            locked=True,
            expires_at=expires_at,
            reference=reference
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

from backend.app.services.credits_service import add_credits

# backend/app/services/credits_service.py (append if file exists)
from decimal import Decimal
from backend.app.db import SessionLocal
from backend.app.models.credit_reservation import CreditReservation
from backend.app.models.credit_transaction import CreditTransaction
from backend.app.models.user import User
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

def capture_reservation_and_charge(reservation_id: int, type_: str = "charge", reference: str = None):
    """
    Convert a reservation into a real charge (transaction).
    This expects a CreditReservation row that was previously created and locked.
    """
    db = SessionLocal()
    try:
        res = db.query(CreditReservation).get(reservation_id)
        if not res or not res.locked:
            raise HTTPException(status_code=404, detail="reservation_not_found_or_already_captured")
        # compute balance (use last transaction or user.credits)
        user = db.query(User).get(res.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")

        # compute new balance using user.credits if present
        balance = Decimal(getattr(user, "credits", 0) or 0)
        new_balance = balance - Decimal(res.amount)
        if new_balance < 0:
            raise HTTPException(status_code=402, detail="insufficient_credits")

        # write transaction
        tr = CreditTransaction(user_id=res.user_id, amount=-Decimal(res.amount), balance_after=new_balance, type=type_, reference=reference or res.reference)
        # mark reservation unlocked
        res.locked = False
        db.add(tr)
        db.add(res)
        if hasattr(user, "credits"):
            user.credits = float(new_balance)
            db.add(user)
        db.commit()
        db.refresh(tr)
        return tr
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("capture_reservation failed: %s", e)
        raise HTTPException(status_code=500, detail="capture_error")
    finally:
        db.close()

def release_reservation_by_job(job_id: str):
    """
    Find reservation(s) by job_id and release them (unlock) — useful on job failure.
    """
    db = SessionLocal()
    try:
        rows = db.query(CreditReservation).filter(CreditReservation.job_id==job_id, CreditReservation.locked==True).all()
        for r in rows:
            r.locked = False
        db.commit()
        return True
    finally:
        db.close()



from backend.app.models.credit_reservation import CreditReservation
from backend.app.models.credit_transaction import CreditTransaction

def capture_reservation_and_charge(reservation_id: int, type_: str = "charge", reference: str = None):
    db = SessionLocal()
    try:
        res = db.query(CreditReservation).get(reservation_id)
        if not res or not res.locked:
            raise HTTPException(status_code=404, detail="reservation_not_found_or_unlocked")
        # team reservation handled by team_billing_service
        if res.team_id:
            from backend.app.services.team_billing_service import capture_team_reservation
            return capture_team_reservation(res.id, type_=type_, reference=reference)
        # user reservation → create transaction and reduce user credits
        user = db.query(User).get(res.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        amt = Decimal(res.amount)
        # ensure user has credits column
        if hasattr(user, "credits"):
            user.credits = float(Decimal(user.credits or 0) - amt)
        tx = CreditTransaction(user_id=res.user_id, amount=-float(amt), balance_after=float(get_user_balance(res.user_id)), type=type_, reference=reference or res.reference)
        res.locked = False
        db.add(tx); db.add(res); db.add(user); db.commit(); db.refresh(tx)
        return {"transaction_id": tx.id}
    finally:
        db.close()

def release_reservation_by_job(job_id: str):
    db = SessionLocal()
    try:
        rows = db.query(CreditReservation).filter(CreditReservation.job_id == job_id, CreditReservation.locked == True).all()
        for r in rows:
            r.locked = False
        db.commit()
        return True
    finally:
        db.close()


# append to backend/app/services/credits_service.py

from backend.app.models.credit_reservation import CreditReservation
from backend.app.models.credit_transaction import CreditTransaction
from decimal import Decimal
from fastapi import HTTPException
import logging
logger = logging.getLogger(__name__)

def capture_reservation_and_charge(reservation_id: int, type_: str = "charge", reference: str = None) -> CreditTransaction:
    """
    Capture a locked reservation and convert into a real debit transaction.
    """
    db = SessionLocal()
    try:
        res = db.get(CreditReservation, reservation_id)
        if not res or not res.locked:
            raise HTTPException(status_code=404, detail="reservation_not_found_or_not_locked")
        # compute current balance
        # We assume user.credits contains current balance OR transactions present.
        user = db.query(User).get(res.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        current_balance = Decimal(getattr(user, "credits", 0) or 0)
        new_balance = current_balance - Decimal(res.amount)
        if new_balance < 0:
            # This should not happen if reservation was validated, but guard anyway.
            raise HTTPException(status_code=402, detail="insufficient_credits")
        # update user balance if field exists
        if hasattr(user, "credits"):
            user.credits = float(new_balance)
            db.add(user)
        tx = CreditTransaction(
            user_id=res.user_id,
            amount = -Decimal(res.amount),
            balance_after = new_balance,
            type = type_,
            reference = reference or res.reference
        )
        res.locked = False
        db.add(tx)
        db.add(res)
        db.commit()
        db.refresh(tx)
        return tx
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("capture_reservation_and_charge failed: %s", e)
        raise HTTPException(status_code=500, detail="capture_failed")
    finally:
        db.close()

def release_reservation_by_job(job_id: str) -> int:
    """
    Release (unlock) all reservations for a job_id and return count released.
    """
    db = SessionLocal()
    try:
        rows = db.query(CreditReservation).filter(CreditReservation.job_id == job_id, CreditReservation.locked == True).all()
        cnt = 0
        for r in rows:
            r.locked = False
            db.add(r)
            cnt += 1
        db.commit()
        return cnt
    finally:
        db.close()


