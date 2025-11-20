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

@router.get("/domains/top-good")
def top_good_domains(limit: int = 50, admin = Depends(get_current_admin)):
    """
    Returns domains with highest good:bad ratio.
    Based on Redis counters.
    """
    import redis, json

    try:
        r = redis.from_url("redis://redis:6379/0")
    except:
        raise HTTPException(500, "redis_not_connected")

    keys = r.keys("domain:*:good")
    final = []

    for k in keys:
        domain = k.decode().split(":")[1]
        good = int(r.get(f"domain:{domain}:good") or 0)
        bad = int(r.get(f"domain:{domain}:bad") or 0)
        total = good + bad
        if total == 0:
            continue
        ratio = good / total
        final.append({
            "domain": domain,
            "good": good,
            "bad": bad,
            "ratio": ratio
        })

    final_sorted = sorted(final, key=lambda x: x["ratio"], reverse=True)
    return final_sorted[:limit]

@router.get("/domains/top-bad")
def top_bad_domains(limit: int = 50, admin = Depends(get_current_admin)):
    import redis
    try:
        r = redis.from_url("redis://redis:6379/0")
    except:
        raise HTTPException(500, "redis_not_connected")

    keys = r.keys("domain:*:bad")
    final = []

    for k in keys:
        domain = k.decode().split(":")[1]
        good = int(r.get(f"domain:{domain}:good") or 0)
        bad = int(r.get(f"domain:{domain}:bad") or 0)
        total = good + bad
        if total == 0:
            continue
        final.append({
            "domain": domain,
            "good": good,
            "bad": bad,
            "fail_rate": bad / total
        })

    final_sorted = sorted(final, key=lambda x: x["fail_rate"], reverse=True)
    return final_sorted[:limit]


@router.get("/domain-trends/{domain}")
def domain_trends(domain: str, admin = Depends(get_current_admin)):
    """
    In future you will store time-series. 
    For now return historical good/bad counts (real-time).
    """
    import redis
    domain = domain.lower()

    try:
        r = redis.from_url("redis://redis:6379/0")
    except:
        raise HTTPException(500, "redis_not_connected")

    good = int(r.get(f"domain:{domain}:good") or 0)
    bad = int(r.get(f"domain:{domain}:bad") or 0)

    return {
        "domain": domain,
        "good": good,
        "bad": bad,
        "trend": "improving" if good > bad else "declining"
    }


@router.get("/deliverability-summary")
def deliverability_summary(admin = Depends(get_current_admin)):
    """
    Aggregated deliverability KPI for admin dashboard.
    """
    import redis
    try:
        r = redis.from_url("redis://redis:6379/0")
    except:
        raise HTTPException(500, "redis_not_connected")

    good_keys = r.keys("domain:*:good")
    bad_keys = r.keys("domain:*:bad")

    good_total = sum(int(r.get(k) or 0) for k in good_keys)
    bad_total = sum(int(r.get(k) or 0) for k in bad_keys)

    total = good_total + bad_total
    if total == 0:
        rate = None
    else:
        rate = round((good_total / total) * 100, 2)

    return {
        "total_emails": total,
        "successful": good_total,
        "failed": bad_total,
        "success_rate_percent": rate
        }



@router.get("/recent-failures")
def recent_failures(limit: int = 100, admin = Depends(get_current_admin)):
    """
    Fetch recent invalid emails from DB.
    """
    db = SessionLocal()
    try:
        rows = db.query(VerificationResult)\
                 .filter(VerificationResult.status == "invalid")\
                 .order_by(VerificationResult.created_at.desc())\
                 .limit(limit).all()

        return [{
            "email": r.email,
            "status": r.status,
            "risk_score": r.risk_score,
            "created_at": r.created_at
        } for r in rows]
    finally:
        db.close()


@router.get("/users")
def admin_list_users(limit: int = 50, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        rows = db.query(User)\
                 .order_by(User.created_at.desc())\
                 .limit(limit).all()
        return [{"id": u.id, "email": u.email, "is_active": u.is_active,
                 "created_at": u.created_at} for u in rows]
    finally:
        db.close()


from backend.app.services.credits_service import get_balance

@router.get("/user/{user_id}/credits")
def admin_user_credits(user_id: int, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        bal = get_balance(db, user_id)
        return {"user_id": user_id, "balance": float(bal)}
    finally:
        db.close()



@router.get("/user/{user_id}/verifications")
def admin_user_verifications(user_id: int, limit: int = 100, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        rows = db.query(VerificationResult)\
                 .filter(VerificationResult.user_id == user_id)\
                 .order_by(VerificationResult.created_at.desc())\
                 .limit(limit).all()

        return [{
            "email": r.email,
            "status": r.status,
            "risk_score": r.risk_score,
            "created_at": r.created_at
        } for r in rows]
    finally:
        db.close()



@router.get("/bulk-jobs")
def admin_bulk_jobs(limit: int = 50, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        rows = db.query(CreditReservation)\
                 .order_by(CreditReservation.created_at.desc())\
                 .limit(limit).all()
        return [{
            "job_id": r.job_id,
            "user_id": r.user_id,
            "amount_reserved": float(r.amount),
            "locked": r.locked,
            "expires_at": r.expires_at,
            "created_at": r.created_at
        } for r in rows]
    finally:
        db.close()


@router.delete("/clear-domain-cache/{domain}")
def clear_domain_cache(domain: str, admin = Depends(get_current_admin)):
    """
    Clears cached reputation for a domain.
    """
    import redis
    try:
        r = redis.from_url("redis://redis:6379/0")
        r.delete(f"domain:reputation:{domain}")
        return {"cleared": domain}
    except:
        raise HTTPException(500, "redis_not_connected")




from backend.app.models.decision_maker import DecisionMaker
from backend.app.db import SessionLocal

@router.get("/decision-makers")
def admin_list_decision_makers(
    company: str = None,
    domain: str = None,
    verified: bool = None,
    limit: int = 100,
    admin = Depends(get_current_admin)
):
    """
    Admin: List decision makers with optional filters.
    """
    db = SessionLocal()
    try:
        q = db.query(DecisionMaker)

        if company:
            q = q.filter(DecisionMaker.company.ilike(f"%{company}%"))
        if domain:
            q = q.filter(DecisionMaker.domain == domain.lower())
        if verified is not None:
            q = q.filter(DecisionMaker.verified == verified)

        q = q.order_by(DecisionMaker.created_at.desc()).limit(limit)
        rows = q.all()

        return [
            {
                "id": r.id,
                "company": r.company,
                "domain": r.domain,
                "name": r.full_name(),
                "title": r.title,
                "email": r.email,
                "source": r.source,
                "verified": r.verified,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    finally:
        db.close()



import csv
from fastapi.responses import StreamingResponse

@router.get("/decision-makers/export")
def export_decision_makers_csv(
    company: str = None,
    domain: str = None,
    verified: bool = None,
    admin = Depends(get_current_admin)
):
    """
    Admin: Export decision makers as CSV file.
    """

    db = SessionLocal()
    try:
        q = db.query(DecisionMaker)

        if company:
            q = q.filter(DecisionMaker.company.ilike(f"%{company}%"))
        if domain:
            q = q.filter(DecisionMaker.domain == domain.lower())
        if verified is not None:
            q = q.filter(DecisionMaker.verified == verified)

        q = q.order_by(DecisionMaker.created_at.desc())
        rows = q.all()

        # generator stream — low memory usage
        def iter_csv():
            header = [
                "id", "company", "domain", "first_name", "last_name",
                "title", "email", "verified", "source", "created_at"
            ]
            yield ",".join(header) + "\n"

            for r in rows:
                yield ",".join([
                    str(r.id or ""),
                    str(r.company or ""),
                    str(r.domain or ""),
                    str(r.first_name or ""),
                    str(r.last_name or ""),
                    str(r.title or ""),
                    str(r.email or ""),
                    str(r.verified),
                    str(r.source or ""),
                    str(r.created_at or "")
                ]) + "\n"

        return StreamingResponse(
            iter_csv(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=decision_makers.csv"}
        )

    finally:
        db.close()


@router.get("/decision-makers/{dm_id}")
def admin_get_decision_maker(dm_id: int, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        r = db.query(DecisionMaker).get(dm_id)
        if not r:
            raise HTTPException(status_code=404, detail="not_found")
        return {
            "id": r.id,
            "company": r.company,
            "domain": r.domain,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "title": r.title,
            "email": r.email,
            "verified": r.verified,
            "source": r.source,
            "raw": r.raw,
            "created_at": r.created_at,
        }
    finally:
        db.close()



@router.delete("/decision-makers/{dm_id}")
def admin_delete_decision_maker(dm_id: int, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        r = db.query(DecisionMaker).get(dm_id)
        if not r:
            raise HTTPException(status_code=404, detail="not_found")

        db.delete(r)
        db.commit()
        return {"deleted": dm_id}

    finally:
        db.close()


from backend.app.models.api_key import ApiKey

@router.get("/api-keys")
def admin_list_api_keys(limit: int = 100, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        rows = db.query(ApiKey).order_by(ApiKey.created_at.desc()).limit(limit).all()
        return [{"id": r.id, "key": r.key, "user_id": r.user_id, "active": r.active, "daily_limit": r.daily_limit, "rate_limit_per_sec": r.rate_limit_per_sec} for r in rows]
    finally:
        db.close()

@router.post("/api-keys/{api_key_id}/update-rate")
def admin_update_api_key_rate(api_key_id: int, rate_limit_per_sec: int, admin = Depends(get_current_admin)):
    db = SessionLocal()
    try:
        ak = db.query(ApiKey).get(api_key_id)
        if not ak:
            raise HTTPException(status_code=404, detail="api_key_not_found")
        ak.rate_limit_per_sec = int(rate_limit_per_sec)
        db.commit()
        return {"id": ak.id, "rate_limit_per_sec": ak.rate_limit_per_sec}
    finally:
        db.close()

    
