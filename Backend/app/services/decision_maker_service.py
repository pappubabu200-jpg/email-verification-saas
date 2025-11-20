import logging
from typing import List, Dict, Any, Optional
from backend.app.db import SessionLocal
from backend.app.services.decision_cache import get_cached, set_cached
from backend.app.services.pdl_client import pdl_search_by_domain
from backend.app.services.apollo_client import apollo_search_people
from backend.app.services.email_pattern_engine import common_patterns
from backend.app.services.verification_engine import verify_email_sync
from backend.app.models.decision_maker import DecisionMaker

logger = logging.getLogger(__name__)

def normalize_person_record(raw: Dict[str, Any], source: str, domain: Optional[str] = None) -> Dict[str, Any]:
    """
    Convert a raw person dict from PDL or Apollo into our normalized format.
    """
    # best-effort parsing (fields vary by provider)
    first = raw.get("first_name") or raw.get("given_name") or raw.get("name") and raw.get("name").split(" ")[0]
    last = raw.get("last_name") or raw.get("family_name") or ""
    title = raw.get("title") or raw.get("job_title") or raw.get("role") or ""
    email = raw.get("email") or raw.get("work_email") or raw.get("contact_email")
    company = raw.get("organization") or raw.get("company") or raw.get("employer") or raw.get("current_employer")
    domain = domain or raw.get("domain") or raw.get("company_domain")
    return {
        "first_name": first,
        "last_name": last,
        "title": title,
        "email": email,
        "company": company,
        "domain": domain,
        "source": source,
        "raw": raw,
    }

def search_decision_makers(domain: Optional[str] = None, company_name: Optional[str] = None, max_results: int = 25, use_cache: bool = True) -> List[Dict[str, Any]]:
    """
    High-level function:
    - tries cache
    - queries PDL & Apollo
    - generates email guesses where missing
    - verifies guessed emails (lightweight)
    - persists top results in DB (optional)
    """
    if not domain and not company_name:
        return []

    query_key = domain if domain else company_name
    if use_cache:
        cached = get_cached(query_key)
        if cached:
            logger.debug("decision cache hit for %s", query_key)
            return cached.get("results", [])

    results: List[Dict[str, Any]] = []

    # 1) People Data Labs
    if domain:
        pdl_people = pdl_search_by_domain(domain, limit=max_results)
        for p in pdl_people:
            norm = normalize_person_record(p, "pdl", domain=domain)
            results.append(norm)

    # 2) Apollo
    try:
        ap_people = apollo_search_people(domain or company_name, limit=max_results)
        for p in ap_people:
            norm = normalize_person_record(p, "apollo", domain=domain)
            results.append(norm)
    except Exception:
        logger.debug("apollo search skipped or failed")

    # 3) Deduplicate by (first,last,title) or email
    dedup = {}
    final = []
    for r in results:
        key = (r.get("email") or "").lower() or ( (r.get("first_name") or "").lower() + "|" + (r.get("last_name") or "").lower() + "|" + (r.get("title") or "").lower())
        if key in dedup:
            continue
        dedup[key] = True
        final.append(r)

    # 4) If no emails, generate with pattern engine for top N
    out = []
    for person in final[:max_results]:
        if person.get("email"):
            # optionally verify quickly (lightweight)
            person["verified_result"] = verify_email_sync(person["email"])
            person["verified"] = person["verified_result"].get("status") == "valid"
        else:
            # generate candidates
            patterns = common_patterns(person.get("first_name"), person.get("last_name"), domain)
            guesses = []
            for cand in patterns:
                # verify guess with verification engine
                vr = verify_email_sync(cand)
                guesses.append({"email": cand, "result": vr})
                if vr.get("status") == "valid":
                    person["email"] = cand
                    person["verified_result"] = vr
                    person["verified"] = True
                    break
            person["guesses"] = guesses
        out.append(person)

    # 5) Persist top N results to DB (optional)
    try:
        db = SessionLocal()
        for p in out[:50]:
            try:
                dm = DecisionMaker(
                    user_id=None,
                    company=p.get("company"),
                    domain=domain,
                    first_name=p.get("first_name"),
                    last_name=p.get("last_name"),
                    title=p.get("title"),
                    email=p.get("email"),
                    source=p.get("source"),
                    raw=str(p.get("raw") or {}),
                    verified=bool(p.get("verified", False))
                )
                db.add(dm)
            except Exception:
                logger.debug("skip persist person")
        db.commit()
    except Exception:
        logger.exception("persist decision makers failed")
    finally:
        try:
            db.close()
        except Exception:
            pass

    # 6) Cache the results
    set_cached(query_key, {"results": out}, ttl=60 * 60 * 24)  # 24h
    return out
