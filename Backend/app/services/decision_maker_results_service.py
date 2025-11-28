# backend/app/services/decision_maker_results_service.py

import csv
import io
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.decision_maker import DecisionMaker


async def get_results_for_job(db: AsyncSession, job_id: str):
    """
    Load all decision makers linked to a discovery job_id.
    Also compute summary stats.
    """
    stmt = select(DecisionMaker).where(DecisionMaker.job_id == job_id)
    res = await db.execute(stmt)
    rows = res.scalars().all()

    if not rows:
        return None

    items = []
    total = len(rows)
    verified = sum(1 for r in rows if r.verified)
    enriched = sum(1 for r in rows if r.enrichment_json)
    domains = len(set(r.company_domain for r in rows if r.company_domain))

    for r in rows:
        items.append({
            "id": r.id,
            "name": r.name,
            "title": r.title,
            "company": r.company,
            "company_domain": r.company_domain,
            "email": r.email,
            "status": "valid" if r.verified else "invalid",
            "enriched": bool(r.enrichment_json),
        })

    summary = {
        "total": total,
        "verified": verified,
        "enriched": enriched,
        "domains": domains,
    }

    return {"items": items, "summary": summary}


async def export_results_csv(db: AsyncSession, job_id: str) -> bytes:
    """
    Return CSV bytes of DM discovery results.
    """
    stmt = select(DecisionMaker).where(DecisionMaker.job_id == job_id)
    res = await db.execute(stmt)
    rows = res.scalars().all()
    if not rows:
        return b""

    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["Name", "Title", "Company", "Domain", "Email", "Status", "Enriched"])

    for r in rows:
        writer.writerow([
            r.name,
            r.title,
            r.company,
            r.company_domain,
            r.email,
            "valid" if r.verified else "invalid",
            "yes" if r.enrichment_json else "no",
        ])

    return buf.getvalue().encode("utf-8")
