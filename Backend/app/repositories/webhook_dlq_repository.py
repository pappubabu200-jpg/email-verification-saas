from backend.app.db import SessionLocal
from backend.app.models.webhook_dlq import WebhookDLQ
import json

class WebhookDLQRepository:
    def save(self, url: str, payload: dict, headers: dict, error: str, attempts: int):
        db = SessionLocal()
        try:
            entry = WebhookDLQ(
                url=url,
                payload=json.dumps(payload),
                headers=json.dumps(headers) if headers else None,
                error_message=error,
                attempts=attempts,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry
        finally:
            db.close()

    def list_failed(self):
        db = SessionLocal()
        try:
            return db.query(WebhookDLQ).filter(WebhookDLQ.resolved == False).all()
        finally:
            db.close()

    def mark_resolved(self, entry_id: int):
        db = SessionLocal()
        try:
            row = db.query(WebhookDLQ).get(entry_id)
            if row:
                row.resolved = True
                db.commit()
                return True
            return False
        finally:
            db.close()
