from fastapi import APIRouter, Query, Depends, HTTPException
from typing import Optional
from backend.app.utils.security import get_current_user
from backend.app.services.decision_maker_service import search_decision_makers

router = APIRouter(prefix="/v1/decision-makers", tags=["Decision Makers"])


@router.get("/search")
def search(domain: Optional[str] = Query(None), company: Optional[str] = Query(None), max_results: int = Query(25, ge=1, le=200), current_user = Depends(get_current_user)):
    """
    Search decision makers by domain or company name.
    Authenticated users only (or support API keys via middleware).
    """
    if not domain and not company:
        raise HTTPException(status_code=400, detail="domain_or_company_required")
    results = search_decision_makers(domain=domain, company_name=company, max_results=max_results)
    return {"query": domain or company, "count": len(results), "results": results}
