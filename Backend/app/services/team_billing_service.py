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
