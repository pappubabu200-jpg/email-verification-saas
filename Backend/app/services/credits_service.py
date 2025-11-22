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

def reserve_and_deduct(user_id: int, amount: Decimal, reference: str=None, team_id: int=None) -> dict:
    """
    Attempt to deduct credits. If team_id provided, try team pool first (team owners decided).
    Behavior:
      - If team_id provided and team has sufficient balance -> deduct from team (use team tx).
      - Else if user has sufficient personal credits -> deduct from user.
      - Else raise 402 insufficient_credits.
    """
    # 1) Try team pool if team_id given
    if team_id:
        try:
            return reserve_and_deduct_team(team_id, amount, reference=reference)
        except HTTPException as e:
            # team insufficient -> fallthrough to user or abort depending policy
            if e.status_code != 402:
                raise
            # else try user balance below

            pass

    # 2) Deduct from user
    db = SessionLocal()
    try:
        user = db.query(User).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user_not_found")
        balance = Decimal(getattr(user, "credits", 0) or 0)
        if balance < amount:
            raise HTTPException(status_code=402, detail="insufficient_credits")
        new_balance = balance - amount
        if hasattr(user, "credits"):
            user.credits = float(new_balance)
            db.add(user)
        tr = CreditTransaction(user_id=user_id, amount=-amount, balance_after=new_balance, type="debit", reference=reference or "")
        db.add(tr)
        db.commit()
        db.refresh(tr)
        return {"balance_after": float(new_balance), "transaction_id": tr.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("reserve_and_deduct failed: %s", e)
        raise HTTPException(status_code=500, detail="credit_error")
    finally:
        db.close()

from backend.app.services.credits_service import add_credits
