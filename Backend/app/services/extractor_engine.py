
# backend/app/services/extractor_engine.py
"""
Extractor Engine (Production Grade)

Features:
- Extract emails, metadata, title, headers from any URL
- HTML parsing using BeautifulSoup
- Fast timeouts + redirect following
- Credit deduction via reserve_and_deduct()
- Bulk-friendly structure (supports Celery workers)
- Optional domain throttle / backoff
- Upload results to MinIO/S3
"""

import re
import time
import logging
import requests
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup

from backend.app.config import settings
from backend.app.services.storage_s3 import upload_file_local_or_s3
from backend.app.services.credits_service import reserve_and_deduct, capture_reservation_and_charge
from backend.app.services.domain_backoff import (
    get_backoff_seconds,
    increase_backoff,
    clear_backoff,
    acquire_slot,
    release_slot,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = float(getattr(settings, "EXTRACTOR_TIMEOUT", 12.0))
USER_AGENT = getattr(
    settings,
    "EXTRACTOR_USER_AGENT",
    "Mozilla/5.0 (compatible; EmailSaaS/1.0; +https://your-domain)"
)


# -------------------------------------------------------------------
# Helper: Extract emails from text
# -------------------------------------------------------------------
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.I)

def extract_emails(text: str) -> List[str]:
    emails = EMAIL_REGEX.findall(text or "")
    seen = set()
    out = []
    for e in emails:
        if e.lower() not in seen:
            out.append(e.lower())
            seen.add(e.lower())
    return out


# -------------------------------------------------------------------
# Core extractor function (single URL)
# -------------------------------------------------------------------
def extract_from_url(
    url: str,
    user_id: Optional[int] = None,
    team_id: Optional[int] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:

    result = {
        "url": url,
        "status": "unknown",
        "title": None,
        "emails": [],
        "meta": {},
        "http_status": None,
        "error": None,
        "duration_sec": 0,
    }

    domain = None
    try:
        domain = url.split("//")[-1].split("/")[0].lower()
    except Exception:
        domain = None

    # Respect domain backoff
    try:
        backoff = get_backoff_seconds(domain)
        if backoff > 0:
            time.sleep(min(backoff, 8))
    except Exception:
        pass

    # Acquire domain slot
    slot = acquire_slot(domain) if domain else True
    if not slot:
        result["status"] = "throttled"
        result["error"] = "domain_slots_full"
        return result

    start = time.time()
    reservation_id = None

    try:
        # ---------------------------------------------------------------
        # Deduct credits BEFORE fetching page
        # key: extractor.single_page → cost from pricing_service
        # ---------------------------------------------------------------
        from backend.app.services.pricing_service import get_cost_for_key
        cost = get_cost_for_key("extractor.single_page")

        if cost > 0:
            r = reserve_and_deduct(
                user_id=user_id,
                team_id=team_id,
                amount=cost,
                reference=f"extract:{url}",
                job_id=None,
            )
            reservation_id = r.get("reservation_id")

        # ---------------------------------------------------------------
        # Actual HTTP request
        # ---------------------------------------------------------------
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        result["http_status"] = resp.status_code

        if resp.status_code >= 400:
            result["status"] = "error"
            result["error"] = f"http_{resp.status_code}"
            increase_backoff(domain)
            return result

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # ---------------------------------------------------------------
        # Extract title
        # ---------------------------------------------------------------
        try:
            title_tag = soup.find("title")
            if title_tag:
                result["title"] = title_tag.get_text(strip=True)
        except Exception:
            pass

        # ---------------------------------------------------------------
        # Extract emails
        # ---------------------------------------------------------------
        text = soup.get_text(separator=" ", strip=True)
        result["emails"] = extract_emails(text)

        # ---------------------------------------------------------------
        # Extract meta tags
        # ---------------------------------------------------------------
        meta_out = {}
        try:
            for tag in soup.find_all("meta"):
                name = tag.get("name") or tag.get("property")
                val = tag.get("content")
                if name and val:
                    meta_out[name.lower()] = val
        except Exception:
            pass
        result["meta"] = meta_out

        result["status"] = "success"
        clear_backoff(domain)

        # ---------------------------------------------------------------
        # Finalize charge (capture reservation)
        # ---------------------------------------------------------------
        if reservation_id:
            db = SessionLocal()
            try:
                capture_reservation_and_charge(
                    db=db,
                    reservation_id=reservation_id,
                    type_="charge",
                    reference=f"extract:{url}",
                )
            finally:
                db.close()

        return result

    except Exception as e:
        logger.exception("extractor failed: %s", e)
        result["status"] = "error"
        result["error"] = str(e)
        try:
            increase_backoff(domain)
        except Exception:
            pass
        return result

    finally:
        try:
            release_slot(domain)
        except Exception:
            pass

        result["duration_sec"] = round(time.time() - start, 3)


# -------------------------------------------------------------------
# Bulk extraction (sync wrapper)
# -------------------------------------------------------------------
def extract_bulk(urls: List[str], user_id: Optional[int] = None, team_id: Optional[int] = None):
    """
    Extract multiple URLs synchronously.
    Returns list of extraction result dicts.
    """
    out = []
    for u in urls:
        try:
            res = extract_from_url(u, user_id=user_id, team_id=team_id)
            out.append(res)
        except Exception as e:
            out.append({
                "url": u,
                "status": "error",
                "error": str(e),
            })
    return out
