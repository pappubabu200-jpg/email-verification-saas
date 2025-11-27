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

    # backend/app/services/decision_maker_service.py
import logging
import asyncio
import time
from typing import Optional, Dict, Any, List
from backend.app.services.apollo_client import apollo_search_person, apollo_enrich_person_by_email
from backend.app.services.pdl_client import pdl_enrich_email
from backend.app.services.cache import get_cached, set_cached, cache_key
from backend.app.services.processing_lock import acquire_processing_key, release_processing_key, wait_for_processing_result
from backend.app.services.redis_rate_limiter import RateLimiter
from backend.app.services.metrics import DM_METRICS  # optional metrics module (see note)
from backend.app.services.credits_service import deduct_credits, check_credits  # adapt to your service
from backend.app.config import settings

logger = logging.getLogger(__name__)
RATE_LIMITER = RateLimiter(redis_url=getattr(settings, "REDIS_URL", None))

# TTL for cached decision maker results
DM_CACHE_TTL = int(getattr(settings, "DM_CACHE_TTL", 3600))


def _normalize_apollo_person(raw: Dict[str, Any]) -> Dict[str, Any]:
    # map Apollo's payload to our UI shape
    # This is best-effort; adapt to actual Apollo response structure
    return {
        "id": raw.get("id") or raw.get("email"),
        "name": raw.get("name") or raw.get("full_name"),
        "email": raw.get("email"),
        "title": raw.get("title"),
        "company": raw.get("company_name") or (raw.get("current_employer") and raw["current_employer"].get("name")),
        "linkedin": raw.get("linkedin_url") or raw.get("linkedin"),
        "confidence": raw.get("confidence_score") or raw.get("score"),
        "raw_apollo": raw,
    }


def _normalize_pdl_person(raw: Dict[str, Any]) -> Dict[str, Any]:
    # map PDL response fields to our internal shape (best-effort)
    return {
        "id": raw.get("uuid") or raw.get("request_id") or raw.get("email"),
        "name": raw.get("full_name") or raw.get("name"),
        "email": raw.get("email"),
        "phone": raw.get("phone"),
        "linkedin": raw.get("linkedin"),
        "company": (raw.get("employment") and raw["employment"].get("organization")),
        "work_history": raw.get("employment_history") or [],
        "raw_pdl": raw,
    }


def _merge_records(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple merge logic: primary has precedence; fill missing keys from secondary.
    Also combine arrays (work_history).
    """
    out = dict(primary)
    for k, v in (secondary or {}).items():
        if k not in out or out.get(k) in (None, "", []):
            out[k] = v
        else:
            # if both lists, merge unique
            if isinstance(out.get(k), list) and isinstance(v, list):
                seen = {str(x) for x in out[k]}
                out[k] = out[k] + [x for x in v if str(x) not in seen]
    return out


async def search_decision_makers(query: str, user_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    High-level search:
    1) Rate limit using sliding-window per user or global
    2) Try cache for query (simple)
    3) Call Apollo search (primary)
    4) For each match, optionally enrich via PDL (background or on demand)
    5) Return normalized list and cache
    """
    key = f"dm:search:{query.lower()}"
    # rate limit per user_id if given
    rl_key = f"dm:rl:user:{user_id}" if user_id else "dm:rl:global"
    allowed, retry = RATE_LIMITER.acquire(rl_key, limit=30, window_seconds=60)  # 30 searches / minute default
    if not allowed:
        raise Exception(f"Rate limit exceeded, retry after {retry} sec")

    # cache lookup
    try:
        cached = await asyncio.to_thread(get_cached, key)
    except Exception:
        cached = None

    if cached:
        return cached.get("results", [])

    # Try to reserve credits (optional)
    if user_id:
        try:
            has = await asyncio.to_thread(check_credits, user_id, 1)  # check at least 1 credit
            if not has:
                raise Exception("Insufficient credits")
        except Exception as e:
            logger.debug("Credit check error/insufficient: %s", e)

    raw = await apollo_search_person(query, limit=limit)
    results: List[Dict[str, Any]] = []
    if raw and isinstance(raw, dict):
        # Apollo may return results in raw['people'] or raw['data']
        entries = raw.get("people") or raw.get("data") or raw.get("results") or []
        for e in entries:
            normalized = _normalize_apollo_person(e)
            # do not do heavy PDL enrich here; frontend can request per-result enrich
            results.append(normalized)

    # cache results (best-effort)
    try:
        await asyncio.to_thread(set_cached, key, {"results": results}, ttl=DM_CACHE_TTL)
    except Exception:
        pass

    return results


async def get_decision_maker_detail(uid_or_email: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Return detailed enriched profile for single DM (by id or email)
    Steps:
      - Check cache
      - Acquire a processing lock to dedupe
      - If lock lost, wait for producer to finish and return cache
      - Call Apollo enrich by email (fast)
      - Call PDL enrich (heavy)
      - Merge, cache, optionally deduct credits
    """
    key = f"dm:detail:{uid_or_email.lower()}"
    # 1) cache
    cached = await asyncio.to_thread(get_cached, key)
    if cached:
        return cached

    got_lock = await acquire_processing_key(key, ttl=60)
    if not got_lock:
        # wait for other's result
        maybe = await wait_for_processing_result(key, poll_interval=0.5, timeout=20)
        if maybe:
            return maybe
        # otherwise continue

    try:
        # 2) Apollo quick enrich (by email if looks like email)
        apollo = None
        if "@" in uid_or_email:
            apollo = await apollo_enrich_person_by_email(uid_or_email)
        else:
            # fallback: search by name/id
            apollo_search = await apollo_search_person(uid_or_email, limit=1)
            candidates = (apollo_search.get("people") or apollo_search.get("data") or []) if apollo_search else []
            if candidates:
                apollo = candidates[0]

        apn = _normalize_apollo_person(apollo or {}) if apollo else {}

        # 3) PDL enrich by email if present
        pdl = None
        email = apn.get("email") or (uid_or_email if "@" in uid_or_email else None)
        if email:
            pdl = await pdl_enrich_email(email)
        pdln = _normalize_pdl_person(pdl or {}) if pdl else {}

        merged = _merge_records(apn, pdln)

        # attach metadata
        merged["_sources"] = {"apollo": bool(apollo), "pdl": bool(pdl)}
        merged["_fetched_at"] = int(time.time())

        # 4) Deduct credits (best-effort)
        if user_id:
            try:
                # attempt to deduct 1 credit for an enrichment
                await asyncio.to_thread(deduct_credits, user_id, 1, reason="dm_enrich")
            except Exception as e:
                logger.debug("Failed to deduct credits (ignored): %s", e)

        # 5) Cache result
        try:
            await asyncio.to_thread(set_cached, key, merged, ttl=DM_CACHE_TTL)
        except Exception:
            logger.debug("Caching dm detail failed")

        return merged

    finally:
        try:
            await release_processing_key(key)
        except Exception:
            pass
async def enqueue_enrichment(uid: str, user_id: Optional[int] = None):
    from backend.app.workers.decision_maker_tasks import dm_enrich_async
    dm_enrich_async.delay(uid, user_id)


