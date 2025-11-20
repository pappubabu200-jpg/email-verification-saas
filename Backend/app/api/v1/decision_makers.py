from fastapi import APIRouter, Query, Depends, HTTPException, Request
from typing import Optional
from backend.app.utils.security import get_current_user
from backend.app.services.decision_maker_service import search_decision_makers
from backend.app.services.decision_quota import check_and_consume, get_usage

router = APIRouter(prefix="/v1/decision-makers", tags=["Decision Makers"])


@router.get("/search")
def search(domain: Optional[str] = Query(None), company: Optional[str] = Query(None),
           max_results: int = Query(25, ge=1, le=200),
           request: Request = None,
           current_user = Depends(get_current_user)):
    """
    Search decision makers by domain or company name.
    Authenticated users only (or support API keys via middleware).
    Enforces per-user daily quota (consumes 1 unit per search).
    """

    # Determine effective user:
    # If API key used, middleware sets request.state.api_user_id
    # We prefer DB user object (current_user). If current_user is None and api_user_id present,
    # you may load user from DB instead. For now we require current_user.
    user = current_user

    if not domain and not company:
        raise HTTPException(status_code=400, detail="domain_or_company_required")

    # Check and consume quota (1 unit per search)
    try:
        used_after, limit = check_and_consume(user, amount=1)
    except HTTPException as e:
        # quota exceeded or auth problems
        raise e

    # Run the actual search (heavy work)
    results = search_decision_makers(domain=domain, company_name=company, max_results=max_results)

    return {
        "query": domain or company,
        "count": len(results),
        "results": results,
        "quota": {"used": used_after, "limit": limit}
                            }
