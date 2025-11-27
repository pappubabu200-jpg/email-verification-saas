
# backend/app/services/dm_autodiscovery.py
import logging
import time
from typing import List, Dict, Optional
from backend.app.services.pdl_client import PDLClient
from backend.app.services.apollo_client import ApolloClient
from backend.app.services.email_pattern_engine import common_patterns
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.decision_cache import set_cached
from backend.app.db import SessionLocal
from backend.app.models.decision_maker import DecisionMaker
from backend.app.services.dm_ws_manager import dm_ws_manager  # ws broadcast manager

logger = logging.getLogger(__name__)


def _normalize(raw: Dict, source: str, domain: Optional[str] = None):
    first = raw.get("first_name") or raw.get("given_name") or (raw.get("name") and raw.get("name").split(" ")[0]) or ""
    last = raw.get("last_name") or raw.get("family_name") or ""
    title = raw.get("title") or raw.get("job_title") or ""
    email = raw.get("email") or raw.get("work_email") or None
    company = raw.get("company") or raw.get("organization") or None
    return {
        "first_name": first,
        "last_name": last,
        "name": f"{first} {last}".strip(),
        "title": title,
        "email": email,
        "company": company,
        "domain": domain or raw.get("domain") or None,
        "source": source,
        "raw": raw,
    }


def discover(domain: Optional[str] = None, company_name: Optional[str] = None, max_results: int = 100, job_id: str = None, user_id: Optional[int] = None) -> List[Dict]:
    """
    Synchronous discovery used by Celery worker.
    Returns final list of normalized records.
    Emits progress via dm_ws_manager.broadcast_job(job_id, payload)
    """
    results = []
    pdl = None
    apollo = None

    try:
        pdl = PDLClient()
    except Exception:
        logger.debug("PDL client not configured")

    try:
        apollo = ApolloClient()
    except Exception:
        logger.debug("Apollo client not configured")

    # Step 1: PDL by domain
    total_added = 0
    sources = []

    if domain and pdl:
        try:
            ppl = pdl.search_people_by_domain(domain, limit=max_results)
            for p in ppl:
                norm = _normalize(p, "pdl", domain)
                results.append(norm)
                total_added += 1
                # broadcast incremental progress
                try:
                    dm_ws_manager.broadcast_job(job_id, {"event": "discover_progress", "job_id": job_id, "added": total_added, "latest": norm})
                except Exception:
                    pass
                if total_added >= max_results:
                    break
        except Exception as e:
            logger.debug("PDL domain search error: %s", e)

    # Step 2: Apollo search (domain or company)
    if apollo and total_added < max_results:
        try:
            q = domain or company_name or ""
            ppl = apollo.search_people(q, limit=(max_results - total_added))
            for p in ppl:
                norm = _normalize(p, "apollo", domain)
                # basic dedupe by email/name
                results.append(norm)
                total_added += 1
                try:
                    dm_ws_manager.broadcast_job(job_id, {"event": "discover_progress", "job_id": job_id, "added": total_added, "latest": norm})
                except Exception:
                    pass
                if total_added >= max_results:
                    break
        except Exception as e:
            logger.debug("Apollo search error: %s", e)

    # dedupe results by email or name+title
    dedup = {}
    cleaned = []
    for r in results:
        key = (r.get("email") or "").lower() or (r.get("name","").lower() + "|" + (r.get("title") or "").lower())
        if key in dedup:
            continue
        dedup[key] = True
        cleaned.append(r)

    final = []
    # light verification or guessing: try verify if email present, else guess top patterns
    for idx, person in enumerate(cleaned[:max_results]):
        # broadcast pre-verify event
        try:
            dm_ws_manager.broadcast_job(job_id, {"event": "discover_check", "job_id": job_id, "index": idx, "person": {"name": person.get("name"), "email": person.get("email")}})
        except Exception:
            pass

        if person.get("email"):
            try:
                vr = verify_email_sync(person["email"])
                person["verified"] = vr.get("status") == "valid"
                person["verified_result"] = vr
            except Exception:
                person["verified"] = False
        else:
            # guess patterns and do a quick verify for the first valid guess
            patterns = common_patterns(person.get("first_name"), person.get("last_name"), domain)
            guesses = []
            for g in patterns[:4]:
                try:
                    vr = verify_email_sync(g)
                    guesses.append({"email": g, "result": vr})
                    if vr.get("status") == "valid":
                        person["email"] = g
                        person["verified"] = True
                        person["verified_result"] = vr
                        break
                except Exception:
                    pass
            person["guesses"] = guesses

        final.append(person)
        # broadcast each finalized record
        try:
            dm_ws_manager.broadcast_job(job_id, {"event": "discover_item", "job_id": job_id, "item": person})
        except Exception:
            pass

    # persist top N to DB (best-effort)
    try:
        db = SessionLocal()
        for p in final:
            try:
                dm = DecisionMaker(
                    name=p.get("name"),
                    first_name=p.get("first_name"),
                    last_name=p.get("last_name"),
                    title=p.get("title"),
                    company=p.get("company"),
                    company_domain=p.get("domain"),
                    email=p.get("email"),
                    linkedin=(p.get("raw") or {}).get("linkedin") if p.get("raw") else None,
                    verified=bool(p.get("verified", False)),
                    enrichment_json=p.get("raw") if p.get("raw") else None,
                )
                db.add(dm)
            except Exception:
                logger.debug("persist skipped for one record")
        db.commit()
    except Exception as e:
        logger.exception("Failed to persist discovered DMs: %s", e)
    finally:
        try:
            db.close()
        except Exception:
            pass

    # Cache results under query (if domain or company_name present)
    try:
        key = domain or company_name
        if key:
            set_cached(key, {"results": final}, ttl=60 * 60 * 24)
    except Exception:
        pass

    # final broadcast: complete
    try:
        dm_ws_manager.broadcast_job(job_id, {"event": "discover_completed", "job_id": job_id, "count": len(final)})
    except Exception:
        pass

    return final
