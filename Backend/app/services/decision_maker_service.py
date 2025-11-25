# backend/app/services/decision_maker_service.py

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


# ---------------------------------------------------------
# Normalizer → Convert Apollo/PDL record into unified schema
# ---------------------------------------------------------
def normalize_person_record(raw: Dict[str, Any], source: str, domain: Optional[str] = None) -> Dict[str, Any]:
    first = (
        raw.get("first_name")
        or raw.get("given_name")
        or (raw.get("name") and raw.get("name").split(" ")[0])
    )
    last = raw.get("last_name") or raw.get("family_name") or ""
    title = raw.get("title") or raw.get("job_title") or raw.get("role") or ""
    email = raw.get("email") or raw.get("work_email") or raw.get("contact_email")
    company = (
        raw.get("organization")
        or raw.get("company")
        or raw.get("employer")
        or raw.get("current_employer")
    )
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


# ---------------------------------------------------------
# MAIN SEARCH PIPELINE
# ---------------------------------------------------------
def search_decision_makers(
    domain: Optional[str] = None,
    company_name: Optional[str] = None,
    max_results: int = 25,
    use_cache: bool = True,
    caller_api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Full Decision Maker Finder Pipeline:
      ✔ Cache → External providers → Normalization → Dedupe
      ✔ Email guessing → SMTP verify → Persist → Cache
    """
    if not domain and not company_name:
        return []

    query_key = domain or company_name

    # -----------------------------------------------------
    # 1. CACHE LOOKUP
    # -----------------------------------------------------
    if use_cache:
        cached = get_cached(query_key)
        if cached:
            logger.debug("decision cache hit: %s", query_key)
            return cached.get("results", [])

    results: List[Dict[str, Any]] = []

    # -----------------------------------------------------
    # 2. QUERY PDL
    # -----------------------------------------------------
    if domain:
        try:
            pdl_people = pdl_search_by_domain(
                domain,
                limit=max_results,
                caller_api_key=caller_api_key,
            )
        except Exception as e:
            logger.debug("PDL search error: %s", e)
            pdl_people = []

        for p in pdl_people:
            results.append(normalize_person_record(p, "pdl", domain=domain))

    # -----------------------------------------------------
    # 3. QUERY APOLLO
    # -----------------------------------------------------
    try:
        ap_people = apollo_search_people(
            domain or company_name,
            limit=max_results,
            caller_api_key=caller_api_key,
        )
        for p in ap_people:
            results.append(normalize_person_record(p, "apollo", domain=domain))
    except Exception as e:
        logger.debug("Apollo search failure: %s", e)

    # -----------------------------------------------------
    # 4. DEDUP (email-based → fallback to name+title)
    # -----------------------------------------------------
    dedup = {}
    cleaned = []

    for r in results:
        key = (r.get("email") or "").lower() or (
            (r.get("first_name") or "").lower()
            + "|"
            + (r.get("last_name") or "").lower()
            + "|"
            + (r.get("title") or "").lower()
        )
        if key in dedup:
            continue
        dedup[key] = True
        cleaned.append(r)

    # -----------------------------------------------------
    # 5. VERIFY OR GUESS EMAIL PATTERNS
    # -----------------------------------------------------
    final_out = []

    for person in cleaned[:max_results]:

        # --- CASE A: Already have email ---
        if person.get("email"):
            try:
                vr = verify_email_sync(person["email"])
                person["verified_result"] = vr
                person["verified"] = vr.get("status") == "valid"
            except Exception as e:
                logger.debug("verify_email error: %s", e)
            final_out.append(person)
            continue

        # --- CASE B: No email → generate patterns ---
        guesses = []
        patterns = common_patterns(
            person.get("first_name"),
            person.get("last_name"),
            domain,
        )

        for cand in patterns:
            try:
                vr = verify_email_sync(cand)
                guesses.append({"email": cand, "result": vr})
                if vr.get("status") == "valid":
                    person["email"] = cand
                    person["verified_result"] = vr
                    person["verified"] = True
                    break
            except Exception:
                pass

        person["guesses"] = guesses
        final_out.append(person)

    # -----------------------------------------------------
    # 6. PERSIST TOP 50 TO DB (do not block failures)
    # -----------------------------------------------------
    try:
        db = SessionLocal()
        for person in final_out[:50]:
            try:
                dm = DecisionMaker(
                    user_id=None,
                    company=person.get("company"),
                    domain=domain,
                    first_name=person.get("first_name"),
                    last_name=person.get("last_name"),
                    title=person.get("title"),
                    email=person.get("email"),
                    source=person.get("source"),
                    raw=str(person.get("raw") or {}),
                    verified=bool(person.get("verified", False)),
                )
                db.add(dm)
            except Exception:
                logger.debug("skipped persist for one record")
        db.commit()
    except Exception as e:
        logger.exception("persist decision makers failed: %s", e)
    finally:
        try:
            db.close()
        except Exception:
            pass

    # -----------------------------------------------------
    # 7. SAVE TO CACHE
    # -----------------------------------------------------
    set_cached(query_key, {"results": final_out}, ttl=60 * 60 * 24)

    return final_out
