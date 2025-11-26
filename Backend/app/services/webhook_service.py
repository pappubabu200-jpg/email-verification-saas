# backend/app/services/webhook_service.py
import json
from typing import Dict, Any
from models.webhook import WebhookEndpoint, WebhookEvent
from db import SessionLocal

# This is the ONLY function you need to call from anywhere in your code
async def trigger_webhook(event_type: str, payload: Dict[str, Any], team_id: int):
    """
    Call this whenever something happens:
    await trigger_webhook("verification.completed", result_dict, team_id)
    await trigger_webhook("bulk_job.finished", job_data, team_id)
    """
    db = SessionLocal()
    try:
        endpoints = db.query(WebhookEndpoint).filter(
            WebhookEndpoint.team_id == team_id,
            WebhookEndpoint.is_active == True,
            WebhookEndpoint.events.contains(event_type)
        ).all()

        for endpoint in endpoints:
            event = WebhookEvent(
                endpoint_id=endpoint.id,
                event_type=event_type,
                payload=json.dumps(payload),
                status="pending"
            )
            db.add(event)
            db.commit()
            db.refresh(event)

            # This uses your existing webhook_sender + dispatcher
            from .webhook_sender import send_webhook
            send_webhook.delay(event.id, endpoint.secret)  # Celery task
    finally:
        db.close()
        # backend/app/services/webhook_service.py
import json
from typing import Dict, Any
from models.webhook import WebhookEndpoint, WebhookEvent
from db import SessionLocal
from .webhook_dispatcher import send_webhook_async

async def trigger_webhook(event_type: str, payload: Dict[str, Any], team_id: int):
    """
    CALL THIS FROM ANYWHERE IN YOUR CODE:
    await trigger_webhook("verification.completed", result, team_id)
    await trigger_webhook("bulk_job.finished", job_data, team_id)
    """
    db = SessionLocal()
    try:
        endpoints = db.query(WebhookEndpoint).filter(
            WebhookEndpoint.team_id == team_id,
            WebhookEndpoint.is_active == True,
            WebhookEndpoint.events.contains(event_type)
        ).all()

        for endpoint in endpoints:
            # Optional: Add HMAC signature here if you want
            event_payload = {
                "event": event_type,
                "data": payload,
                "timestamp": __import__("time").time(),
                "webhook_id": endpoint.id
            }

            # Create DB record (optional but recommended for logs/retries)
            event = WebhookEvent(
                endpoint_id=endpoint.id,
                event_type=event_type,
                payload=json.dumps(event_payload),
                status="pending"
            )
            db.add(event)
            db.commit()

            # Fire your existing Celery task
            send_webhook_async.delay(endpoint.url, event_payload)

    except Exception as e:
        print(f"Webhook trigger error: {e}")
    finally:
        db.close()
        
