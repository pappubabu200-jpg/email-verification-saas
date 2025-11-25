# backend/app/repositories/webhook_dlq_repository.py

from datetime import datetime
from typing import Optional, List, Dict, Any
from backend.app.db import SessionLocal
from backend.app.models.webhook_dlq import WebhookDLQ


class WebhookDLQRepository:
    """
    Repository for Webhook Dead-Letter Queue entries.
    Fully production-grade:
    - JSON-safe storage (payload + headers)
    - Mark processed
    - Increment attempts
    - List all or only failed
    """

    def save(self,
             url: str,
             payload: Dict[str, Any] | str,
             headers: Dict[str, str] | None = None,
             error: str | None = None,
             attempts: int = 0) -> WebhookDLQ:
        """
        Save a permanently failed webhook entry into DLQ.
        """
        db = SessionLocal()
        try:
            entry = WebhookDLQ(
                url=url,
                payload=payload if isinstance(payload, (dict, list)) else payload,
                headers=headers,
                error=error,
                attempts=attempts,
                processed=False,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry
        finally:
            db.close()

    def list(self,
             limit: int = 100,
             offset: int = 0,
             only_unprocessed: bool = True) -> List[WebhookDLQ]:
        """
        List DLQ entries.
        Set only_unprocessed=False -> fetch ALL entries.
        """
        db = SessionLocal()
        try:
            q = db.query(WebhookDLQ)
            if only_unprocessed:
                q = q.filter(WebhookDLQ.processed == False)

            return q.order_by(WebhookDLQ.created_at.asc()) \
                    .limit(limit) \
                    .offset(offset) \
                    .all()
        finally:
            db.close()

    def get(self, entry_id: int) -> Optional[WebhookDLQ]:
        db = SessionLocal()
        try:
            return db.query(WebhookDLQ).get(entry_id)
        finally:
            db.close()

    def mark_processed(self, entry_id: int) -> bool:
        """
        Mark a DLQ entry as resolved.
        """
        db = SessionLocal()
        try:
            entry = db.query(WebhookDLQ).get(entry_id)
            if not entry:
                return False

            entry.processed = True
            entry.processed_at = datetime.utcnow()

            db.add(entry)
            db.commit()
            return True
        finally:
            db.close()

    def delete(self, entry_id: int) -> bool:
        """
        Permanently delete DLQ entry.
        """
        db = SessionLocal()
        try:
            entry = db.query(WebhookDLQ).get(entry_id)
            if not entry:
                return False

            db.delete(entry)
            db.commit()
            return True
        finally:
            db.close()

    def increment_attempts(self, entry_id: int, error: str | None = None) -> None:
        """
        Increment retry attempts + update last error message.
        """
        db = SessionLocal()
        try:
            entry = db.query(WebhookDLQ).get(entry_id)
            if not entry:
                return

            entry.attempts = (entry.attempts or 0) + 1
            if error:
                entry.error = error

            db.add(entry)
            db.commit()
        finally:
            db.close()
