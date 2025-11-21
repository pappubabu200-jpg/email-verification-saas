from typing import Optional
from backend.app.db import SessionLocal
from backend.app.models.plan import Plan
import logging

logger = logging.getLogger(__name__)

DEFAULT_PLANS = [
    {"name":"free","display_name":"Free","monthly_price_usd":0,"daily_search_limit":20,"monthly_credit_allowance":0,"rate_limit_per_sec":1},
    {"name":"pro","display_name":"Pro","monthly_price_usd":29.0,"daily_search_limit":200,"monthly_credit_allowance":10000,"rate_limit_per_sec":5},
    {"name":"team","display_name":"Team","monthly_price_usd":199.0,"daily_search_limit":2000,"monthly_credit_allowance":100000,"rate_limit_per_sec":10},
    {"name":"enterprise","display_name":"Enterprise","monthly_price_usd":0,"daily_search_limit":0,"monthly_credit_allowance":0,"rate_limit_per_sec":0},
]

def seed_default_plans():
    db = SessionLocal()
    try:
        for p in DEFAULT_PLANS:
            existing = db.query(Plan).filter(Plan.name == p["name"]).first()
            if not existing:
                plan = Plan(**p)
                db.add(plan)
        db.commit()
    except Exception as e:
        logger.exception("seed_default_plans failed: %s", e)
    finally:
        db.close()

def get_plan_by_name(name: str) -> Optional[Plan]:
    db = SessionLocal()
    try:
        return db.query(Plan).filter(Plan.name == name).first()
    finally:
        db.close()

def get_all_plans():
    db = SessionLocal()
    try:
        return db.query(Plan).order_by(Plan.monthly_price_usd).all()
    finally:
        db.close()
