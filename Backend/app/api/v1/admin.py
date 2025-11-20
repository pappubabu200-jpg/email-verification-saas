from fastapi import APIRouter, Depends, HTTPException
from backend.app.utils.security import get_current_admin
from backend.app.services.deliverability_monitor import compute_domain_score
from backend.app.services.mx_lookup import choose_mx_for_domain

router = APIRouter(prefix="/v1/admin", tags=["Admin"])

# --- Existing endpoints above ---


@router.get("/domain-reputation/{domain}")
def get_domain_reputation(domain: str, admin = Depends(get_current_admin)):
    """
    Admin endpoint:
    Returns full deliverability intelligence for a domain.
    Includes MX info, IP info, historical reputation, scores.
    """
    domain = domain.lower()

    # MX lookup
    mx_hosts = choose_mx_for_domain(domain)
    mx_used = mx_hosts[0] if mx_hosts else None

    # Deliverability score
    try:
        reputation = compute_domain_score(domain, mx_used)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"score_failed: {str(e)}")

    return {
        "domain": domain,
        "mx_used": mx_used,
        "reputation": reputation
  }
