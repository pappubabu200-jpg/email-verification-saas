from unittest.mock import patch
from backend.app.services.verification_engine import verify_email_sync

def test_verification_engine_valid(monkeypatch):
    # mock MX lookup
    monkeypatch.setattr(
        "backend.app.services.verification_engine.choose_mx_for_domain",
        lambda d: ["mx.test"]
    )

    # mock smtp_probe
    monkeypatch.setattr(
        "backend.app.services.verification_engine.smtp_probe",
        lambda email, domain, mx: {
            "mx_host": "mx.test",
            "rcpt_response_code": 250,
            "rcpt_response_msg": "OK"
        }
    )

    out = verify_email_sync("user@test.com")

    assert out["status"] == "valid"
    assert out["risk_score"] == 5
