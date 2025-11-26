# backend/tests/test_webhook_idempotency.py
import pytest
from sqlalchemy.exc import IntegrityError
from backend.app.db import SessionLocal
from backend.app.models import WebhookEvent  # Make sure this model exists


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_idempotency_prevents_duplicate_stripe_event_id(db_session):
    """Ensure the same Stripe event ID cannot be processed twice."""
    event_id = "evt_1J1234567890abcdef12345678"

    # First insertion should succeed
    first_event = WebhookEvent(stripe_event_id=event_id, payload={}, processed=False)
    db_session.add(first_event)
    db_session.commit()

    # Second insertion with same event_id should fail due to unique constraint
    duplicate_event = WebhookEvent(stripe_event_id=event_id, payload={}, processed=False)
    db_session.add(duplicate_event)

    with pytest.raises(IntegrityError) as exc:
        db_session.commit()

    assert "UNIQUE constraint failed" in str(exc.value) or "Duplicate entry" in str(exc.value)

    # Clean up
    db_session.rollback()
