
# backend/app/services/reservation_finalizer.py
"""
Helpers to finalize reservations for a job:
- capture needed reservations (user or team)
- release unused reservations
Used by workers (bulk_tasks, extractor tasks).
"""

from backend.app.db import SessionLocal
from backend.app.models.credit_reservation import CreditReservation
from backend.app.services.credits_service import capture_reservation_and_charge, release_reservation_by_job
from backend.app.services.team_billing_service import capture_team_reservation, add_team_credits
from backend.app.services.credits_service import add_credits
from backend.app.services.pricing_service import get_cost_for_key
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

def finalize_reservations_for_job(job_id: str, user_id: int, processed_count: int, is_team: bool=False, team_id: int=None):
    """
    Finalize reservations linked to job_id by capturing up to actual_cost and releasing the rest.
    """
    db = SessionLocal()
    try:
        reservations = db.query(CreditReservation).filter(CreditReservation.job_id == job_id, CreditReservation.locked == True).order_by(CreditReservation.created_at.asc()).all()
        if not reservations:
            logger.debug("no reservations found for job %s", job_id)
            return

        cost_per = Decimal(str(get_cost_for_key("verify.bulk_per_email") or 0))
        actual_cost = (cost_per * Decimal(processed_count)).quantize(Decimal("0.000001"))
        to_capture = actual_cost
        for r in reservations:
            amt = Decimal(r.amount)
            if to_capture <= 0:
                # release remaining
                r.locked = False
                db.add(r)
                continue
            if amt <= to_capture:
                # capture reservation
                try:
                    if r.reference and str(r.reference).startswith("team:"):
                        # team reservation: capture via team service
                        capture_team_reservation(r.id, type_="bulk_capture", reference=f"bulk:{job_id}")
                    else:
                        capture_reservation_and_charge(r.id, type_="bulk_capture", reference=f"bulk:{job_id}")
                except Exception:
                    logger.exception("capture failed for reservation %s", r.id)
                to_capture -= amt
            else:
                # partial: capture part and release remainder is complex — simplest: capture full reservation then refund the leftover amount immediately
                try:
                    capture_reservation_and_charge(r.id, type_="bulk_capture", reference=f"bulk:{job_id}")
                    leftover = amt - to_capture
                    # refund leftover to the proper owner
                    if r.reference and str(r.reference).startswith("team:"):
                        # parse team id and refund the leftover back to team
                        parts = str(r.reference).split(":")
                        if len(parts) >= 2:
                            try:
                                tid = int(parts[1])
                                add_team_credits(tid, leftover, reference=f"bulk:refund:{job_id}")
                            except Exception:
                                logger.exception("refund leftover to team failed")
                    else:
                        try:
                            add_credits(r.user_id, leftover, reference=f"bulk:refund:{job_id}")
                        except Exception:
                            logger.exception("refund leftover to user failed")
                except Exception:
                    logger.exception("partial capture failed for reservation %s", r.id)
                to_capture = Decimal("0")
        db.commit()
    finally:
        db.close()
