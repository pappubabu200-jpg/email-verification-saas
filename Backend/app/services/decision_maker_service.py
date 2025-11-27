# backend/app/services/decision_maker_service.py
"""
Decision Maker Service (FINAL VERSION)
-------------------------------------
✓ Async architecture
✓ Fast search (Apollo)
✓ Enrichment (PDL + Apollo)
✓ Processing lock + cache
✓ Rate limiter
✓ Credits deduction
✓ WebSocket live push (dm_ws_manager)
✓ Fully compatible with your Frontend DM Search & Detail UI
"""

import time
import logging
import asyncio
from typing import Dict, Any, List, Optional

from backend.app.services.cache import get_cached, set_cached
from backend.app.services.processing_lock import (
    acquire_processing_key,
    release_processing_key,
    wait_for_processing_result,
)
from backend.app.services.redis_rate_limiter import RateLimiter
from backend.app.services.apollo_client import (
    apollo_search_person,
    apollo_enrich_person_by_email,
)
from backend.app.services.pdl_client import pdl_enrich_email
from backend.app.services.credits_service import check_credits, deduct_credits
from backend.app.services.dm_ws_manager import dm_ws_manager
from backend.app.config import settings

logger = logging.getLogger(__name__)

# ------------------------------------
# Rate Limiter
# ------------------------------------
RATE_LIMITER = RateLimiter(redis_url=settings.REDIS_URL)

# Cache TTL
DM_CACHE_TTL = 3600  # 1 hour


# --------------------------------------------------------
# Normalizers
# --------------------------------------------------------
def _normalize_apollo(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not raw:
        return {}

    return {
        "id": raw.get("id") or raw.get("email"),
        "name": raw.get("name") or raw.get("full_name"),
        "email": raw.get("email"),
        "title": raw.get("title"),
        "company": raw.get("company_name"),
        "domain": raw.get("domain"),
        "linkedin": raw.get("linkedin_url"),
        "confidence": raw.get("confidence_score"),
        "raw": raw,
    }


def _normalize_pdl(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not raw:
        return {}

    emp = raw.get("employment") or {}
    return {
        "id": raw.get("id") or raw.get("email"),
        "name": raw.get("full_name"),
        "email": raw.get("email"),
        "phone": raw.get("phone"),
        "linkedin": raw.get("linkedin"),
        "company": emp.get("organization"),
        "location": raw.get("location"),
        "work_history": raw.get("employment_history", []),
        "raw": raw,
    }


def _merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if not out.get(k):
            out[k] = v
        elif isinstance(out[k], list) and isinstance(v, list):
            # merge unique list values
            seen = {str(x) for x in out[k]}
            out[k] += [x for x in v if str(x) not in seen]
    return out


# --------------------------------------------------------
# SEARCH DECISION MAKERS
# --------------------------------------------------------
async def search_decision_makers(query: str, user_id: Optional[int] = None, limit: int = 12):
    """
    Fast Apollo-based search.
    PDL is NOT called in search (slow) → Only on detail page.
    """
    query = (query or "").strip().lower()
    if not query:
        return []

    cache_key = f"dm:search:{query}"

    # Rate limit
    rl_key = f"dm:search:{user_id or 'global'}"
    allowed, retry = RATE_LIMITER.acquire(rl_key, limit=40, window_seconds=60)
    if not allowed:
        raise Exception(f"Rate limited. Retry in {retry} seconds.")

    # Cache lookup
    try:
        cached = await asyncio.to_thread(get_cached, cache_key)
        if cached:
            return cached["results"]
    except Exception:
        pass

    # Apollo search
    try:
        raw = await apollo_search_person(query, limit=limit)
        entries = (
            raw.get("people")
            or raw.get("data")
            or raw.get("results")
            or []
        )

        results = [_normalize_apollo(e) for e in entries]
    except Exception as e:
        logger.error("Apollo search failed: %s", e)
        results = []

    # Save cache
    try:
        await asyncio.to_thread(set_cached, cache_key, {"results": results}, ttl=DM_CACHE_TTL)
    except Exception:
        pass

    return results


# --------------------------------------------------------
# GET DECISION MAKER DETAIL
# --------------------------------------------------------
async def get_decision_maker_detail(identifier: str, user_id: Optional[int] = None):
    """
    identifier may be: email OR apollo-id
    Steps:
    ✔ Check cache
    ✔ Processing lock
    ✔ Apollo enrich
    ✔ PDL enrich
    ✔ Merge + cache
    ✔ Deduct credits
    ✔ WebSocket push events
    """
    key = f"dm:detail:{identifier.lower()}"

    # Cache
    cached = await asyncio.to_thread(get_cached, key)
    if cached:
        return cached

    # Acquire lock
    got = await acquire_processing_key(key)
    if not got:
        # Wait for result of someone else
        maybe = await wait_for_processing_result(key)
        if maybe:
            return maybe

    try:
        # ------------------------------
        # Apollo Enrich
        # ------------------------------
        if "@" in identifier:
            apollo = await apollo_enrich_person_by_email(identifier)
        else:
            apollo_result = await apollo_search_person(identifier, limit=1)
            entries = (
                apollo_result.get("people")
                or apollo_result.get("data")
                or []
            )
            apollo = entries[0] if entries else None

        ap = _normalize_apollo(apollo)

        # ------------------------------
        # PDL Enrich
        # ------------------------------
        pdl = None
        email = ap.get("email") or (identifier if "@" in identifier else None)

        if email:
            try:
                pdl = await pdl_enrich_email(email)
            except Exception as e:
                logger.debug("PDL enrich failed: %s", e)

        pd = _normalize_pdl(pdl)

        # ------------------------------
        # MERGE BOTH
        # ------------------------------
        merged = _merge(ap, pd)
        merged["_fetched_at"] = int(time.time())

        # ------------------------------
        # Deduct 1 credit (best-effort)
        # ------------------------------
        if user_id:
            try:
                has = await asyncio.to_thread(check_credits, user_id, 1)
                if has:
                    await asyncio.to_thread(deduct_credits, user_id, 1, reason="dm_enrich")
            except Exception:
                pass

        # ------------------------------
        # Cache it
        # ------------------------------
        await asyncio.to_thread(set_cached, key, merged, ttl=DM_CACHE_TTL)

        # ------------------------------
        # Live WebSocket notify
        # ------------------------------
        try:
            asyncio.create_task(
                dm_ws_manager.push(identifier, {
                    "event": "dm_detail_ready",
                    "id": identifier,
                    "data": merged
                })
            )
        except Exception:
            pass

        return merged

    finally:
        await release_processing_key(key)


# --------------------------------------------------------
# Trigger background enrichment via Celery
# --------------------------------------------------------
async def enqueue_enrichment(identifier: str, user_id: Optional[int] = None):
    from backend.app.workers.decision_maker_tasks import dm_enrich_async
    dm_enrich_async.delay(identifier, user_id)
