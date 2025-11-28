# backend/app/workers/dm_discovery_worker.py

import json
import logging
from celery import shared_task

from backend.app.db import SessionLocal
from backend.app.services.apollo_client import apollo_search_people
from backend.app.services.pdl_client import pdl_search_by_domain
from backend.app.services.email_pattern_engine import common_patterns
from backend.app.services.verification_engine import verify_email_sync
from backend.app.services.dm_ws_manager import dm_ws_manager
from backend.app.models.decision_maker import DecisionMaker

logger = logging.getLogger(__name__)


@shared_task(name="dm.discovery")
def dm_discovery_worker(job_id: str, domain: str, user_id: int):
    """
    Run full discovery:
    - Fetch PDL + Apollo people
    - Normalize & dedupe
    - Guess emails
    - Verify emails
    - Persist
    - Stream progress via WebSocket
    """
    session = SessionLocal()
    try:

        # -------------------------------
        # 1) Fetch from providers
        # -------------------------------
        try:
            pdl = pdl_search_by_domain(domain, limit=50)
        except:
            pdl = []

        try:
            apollo = apollo_search_people(domain, limit=50)
        except:
            apollo = []

        raw = pdl + apollo

        total = len(raw)
        processed = 0
        saved_count = 0

        for person in raw:
            processed += 1

            # Normalize
            first = person.get("first_name") or ""
            last = person.get("last_name") or ""
            title = person.get("title") or ""
            company = person.get("company") or ""
            email = person.get("email")

            # Guess email if missing
            verified = False
            verified_info = None

            if email:
                try:
                    vr = verify_email_sync(email)
                    verified = vr.get("status") == "valid"
                    verified_info = vr
                except:
                    pass
            else:
                # brute force patterns
                patterns = common_patterns(first, last, domain)
                for cand in patterns:
                    try:
                        vr = verify_email_sync(cand)
                        if vr.get("status") == "valid":
                            email = cand
                            verified = True
                            verified_info = vr
                            break
                    except:
                        pass

            # Save record
            dm = DecisionMaker(
                job_id=job_id,
                user_id=user_id,
                name=f"{first} {last}".strip(),
                title=title,
                company=company,
                company_domain=domain,
                email=email,
                verified=verified,
                enrichment_json=None,
                raw_json=json.dumps(person),
            )
            session.add(dm)
            saved_count += 1

            # WS progress
            try:
                import asyncio
                asyncio.run(
                    dm_ws_manager.broadcast_job(job_id, {
                        "event": "progress",
                        "total": total,
                        "processed": processed,
                        "saved": saved_count,
                    })
                )
            except:
                pass

        session.commit()

        # Completed
        try:
            import asyncio
            asyncio.run(
                dm_ws_manager.broadcast_job(job_id, {
                    "event": "completed",
                    "total": total,
                    "processed": processed,
                    "saved": saved_count,
                })
            )
        except:
            pass

        logger.info(f"DM Discovery Completed: job={job_id}")

    except Exception as e:
        session.rollback()
        logger.exception("DM discovery failed")

        # Broadcast failure
        try:
            import asyncio
            asyncio.run(
                dm_ws_manager.broadcast_job(job_id, {
                    "event": "failed",
                    "error": "discovery_failed",
                })
            )
        except:
            pass

    finally:
        session.close()
