# backend/app/api/v1/pricing.py
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from backend.app.utils.security import get_current_admin
import logging

router = APIRouter(prefix="/api/v1/pricing", tags=["pricing"])
logger = logging.getLogger(__name__)

# pricing service read-only (fallbacks)
try:
    from backend.app.services.pricing_service import get_pricing_map, get_cost_for_key, DEFAULT_PRICING
    PRICING_AVAILABLE = True
except Exception:
    PRICING_AVAILABLE = False

@router.get("/", response_model=Dict[str, float])
def get_pricing():
    """
    Return current pricing map (cost in credits or units per key).
    """
    if PRICING_AVAILABLE:
        return get_pricing_map()
    return DEFAULT_PRICING if "DEFAULT_PRICING" in globals() else {}

@router.get("/cost/{key}")
def get_cost(key: str):
    """
    Get cost for a single pricing key.
    """
    if PRICING_AVAILABLE:
        return {"key": key, "cost": float(get_cost_for_key(key))}
    raise HTTPException(status_code=501, detail="pricing_service_missing")

@router.post("/override", dependencies=[Depends(get_current_admin)])
def override_pricing(payload: Dict[str, float]):
    """
    Admin: override pricing map in-memory.
    Note: persistent override requires DB migration / config; if pricing_service exposes setter, it will be used.
    """
    if not PRICING_AVAILABLE:
        raise HTTPException(status_code=501, detail="pricing_service_missing")
    # attempt to call optional setter
    try:
        setter = getattr(__import__("backend.app.services.pricing_service", fromlist=[""]), "set_pricing_map", None)
        if callable(setter):
            setter(payload)
            return {"ok": True}
    except Exception:
        logger.exception("pricing override setter failed")

    # fallback: not supported
    raise HTTPException(status_code=501, detail="override_not_supported")
