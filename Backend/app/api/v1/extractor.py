# backend/app/api/v1/extractor.py
import io
import uuid
import csv
import zipfile
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from backend.app.utils.security import get_current_user
from backend.app.services.pricing_service import get_cost_for_key
from backend.app.services.credits_service import reserve_and_deduct, add_credits, get_user_balance
from backend.app.services.plan_service import get_plan_by_name
from backend.app.db import SessionLocal

# extraction engine (assumed to exist). Fallback if not.
try:
    from backend.app.services.extractor_engine import extract_url
except Exception:
    extract_url = None  # we'll fallback to a safe stub

router = APIRouter(prefix="/api/v1/extractor", tags=["extractor"])
logger = logging.getLogger(__name__)

# helper quantize
def _dec(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

class SingleExtractIn(BaseModel):
    url: str
    parse_links: Optional[bool] = False

def _parse_urls_from_text(text: str) -> List[str]:
    """Naive URL line parser — split lines, strip, ignore empties."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        out.append(s)
    return out

def _extract_single(url: str, parse_links: bool = False) -> Dict[str, Any]:
    """Call the extractor engine if present, else return placeholder."""
    try:
        if extract_url:
            return extract_url(url, parse_links=parse_links)
        else:
            # placeholder: return empty result with url
            return {"url": url, "emails": [], "links_found": []}
    except Exception as e:
        logger.exception("extract_url failed for %s: %s", url, e)
        return {"url": url, "error": "extract_failed"}

# -------------------------
# Single synchronous extract
# -------------------------
@router.post("/single", response_model=Dict[str, Any])
def single_extract(payload: SingleExtractIn, request: Request, current_user = Depends(get_current_user)):
    """
    Single URL extraction (sync).
    Charges: pricing key "extractor.single_page"
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    # enforce simple plan limit (max 1 per call)
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and 1 > plan.daily_search_limit:
            # unlikely, but keep check for consistency
            raise HTTPException(status_code=429, detail="plan_limits_restriction")

    cost_per = _dec(get_cost_for_key("extractor.single_page") or 0)
    estimated_cost = cost_per

    job_id = f"ext-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    # reserve upfront
    try:
        reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=reserve_ref) if estimated_cost > 0 else {"balance_after": float(get_user_balance(user.id))}
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # perform extraction
    try:
        res = _extract_single(payload.url, parse_links=payload.parse_links)
    except Exception as e:
        # refund
        try:
            add_credits(user.id, estimated_cost, reference=f"{job_id}:refund_on_error")
        except Exception:
            logger.exception("refund failed for %s", job_id)
        raise HTTPException(status_code=500, detail="extraction_failed")

    # actual cost = cost_per (single)
    actual_cost = estimated_cost
    refund_amount = Decimal("0")

    # if we want to implement usage-based refunds (e.g., zero results -> refund partial), implement here.
    # For now, full charge; optionally refund if no emails found:
    try:
        emails_found = 0
        if isinstance(res, dict) and res.get("emails"):
            emails_found = len(res.get("emails") or [])
        # Example policy: if no emails found, refund 50% (change as you like)
        if emails_found == 0 and estimated_cost > 0:
            refund_amount = (estimated_cost * Decimal("0.5")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            add_credits(user.id, refund_amount, reference=f"{job_id}:partial_refund_no_emails")
    except Exception:
        logger.exception("post-charge refund logic failed for %s", job_id)

    return {
        "job_id": job_id,
        "url": payload.url,
        "result": res,
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost - refund_amount),
        "refund_amount": float(refund_amount),
        "reserve_tx": reserve_res
    }

# -------------------------
# Bulk upload extractor
# -------------------------
@router.post("/bulk-upload", response_model=Dict[str, Any])
async def bulk_extract(file: UploadFile = File(...), request: Request = None, current_user = Depends(get_current_user)):
    """
    Accepts:
      - CSV file (rows containing URLs in any column that looks like 'url' or just plain one-url-per-line)
      - ZIP file containing .csv/.txt files with URLs (one per line or CSV)
    Billing:
      - cost per url = pricing key "extractor.bulk_per_url"
      - reserve upfront for all detected URLs
    Returns job_id, counts, and immediate results (be careful with very large uploads — use async job in production).
    """
    user = current_user
    if not user:
        raise HTTPException(status_code=401, detail="auth_required")

    # read upload into memory (be mindful of large files)
    content = await file.read()
    filename = (file.filename or "").lower()

    # helper: collect urls
    urls: List[str] = []

    try:
        if filename.endswith(".zip") or (file.content_type == "application/zip"):
            # parse zip
            z = zipfile.ZipFile(io.BytesIO(content))
            for name in z.namelist():
                if name.endswith("/") or name.startswith("__MACOSX"):
                    continue
                # only process small text-like files
                if name.lower().endswith((".txt", ".csv")):
                    raw = z.read(name).decode("utf-8", errors="ignore")
                    if name.lower().endswith(".csv"):
                        # try parse csv and look for 'url' columns or first column
                        try:
                            reader = csv.reader(io.StringIO(raw))
                            for row in reader:
                                if not row:
                                    continue
                                # naive: use first non-empty column
                                for col in row:
                                    v = col.strip()
                                    if v:
                                        urls.append(v)
                                        break
                        except Exception:
                            # fallback to line parser
                            urls.extend(_parse_urls_from_text(raw))
                    else:
                        urls.extend(_parse_urls_from_text(raw))
            # done zip
        elif filename.endswith(".csv") or file.content_type in ("text/csv", "application/csv"):
            s = content.decode("utf-8", errors="ignore")
            # parse csv, extract columns that look like URL/email
            try:
                reader = csv.reader(io.StringIO(s))
                for row in reader:
                    if not row:
                        continue
                    for col in row:
                        v = col.strip()
                        if v:
                            urls.append(v)
                            break
            except Exception:
                urls = _parse_urls_from_text(s)
        else:
            # treat as plain text
            s = content.decode("utf-8", errors="ignore")
            urls = _parse_urls_from_text(s)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="invalid_zip")
    except Exception as e:
        logger.exception("bulk parse failed: %s", e)
        raise HTTPException(status_code=400, detail="parse_failed")

    # Deduplicate and sanitize URLs
    urls = [u.strip() for u in urls if u and len(u.strip()) > 0]
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    total_urls = len(unique_urls)
    if total_urls == 0:
        raise HTTPException(status_code=400, detail="no_urls_found")

    # enforce plan daily_search_limit if present (max per single bulk)
    if hasattr(user, "plan") and user.plan:
        plan = get_plan_by_name(user.plan)
        if plan and plan.daily_search_limit and total_urls > plan.daily_search_limit:
            raise HTTPException(status_code=429, detail=f"bulk_size_exceeds_plan_limit ({plan.daily_search_limit})")

    # pricing & reservation
    per_url_cost = _dec(get_cost_for_key("extractor.bulk_per_url") or 0)
    estimated_cost = (per_url_cost * Decimal(total_urls)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    job_id = f"ext-bulk-{uuid.uuid4().hex[:12]}"
    reserve_ref = f"{job_id}:reserve"

    try:
        reserve_res = reserve_and_deduct(user.id, estimated_cost, reference=reserve_ref) if estimated_cost > 0 else {"balance_after": float(get_user_balance(user.id))}
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    # perform extraction for each URL (synchronous here; for production use background worker)
    results: List[Dict[str, Any]] = []
    success_count = 0
    for url in unique_urls:
        try:
            r = _extract_single(url, parse_links=False)
            results.append({"url": url, "result": r})
            # basic success detection
            if isinstance(r, dict) and (r.get("emails") or r.get("links_found")):
                success_count += 1
        except Exception as e:
            logger.exception("extract failed for %s: %s", url, e)
            results.append({"url": url, "error": "extract_failed"})

    # compute actual cost (we keep policy: charge for every URL attempted)
    actual_cost = (per_url_cost * Decimal(total_urls)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # refund policy: example - if extractor failed for more than 50% urls, refund 50% of cost
    failed_count = total_urls - success_count
    refund_amount = Decimal("0")
    try:
        if total_urls > 0 and failed_count / total_urls >= 0.5:
            # refund 50%
            refund_amount = (actual_cost * Decimal("0.5")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            add_credits(user.id, refund_amount, reference=f"{job_id}:refund_bulk_failure")
    except Exception:
        logger.exception("bulk refund failed for %s", job_id)

    return {
        "job_id": job_id,
        "total_urls": total_urls,
        "returned": len(results),
        "estimated_cost": float(estimated_cost),
        "actual_cost": float(actual_cost - refund_amount),
        "refund_amount": float(refund_amount),
        "reserve_tx": reserve_res,
        "results_preview": results[:200]  # keep this payload bounded (avoid huge responses)
}
