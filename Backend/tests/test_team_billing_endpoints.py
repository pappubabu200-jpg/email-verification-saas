# backend/tests/test_team_billing_endpoints.py
import json
import uuid
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

# import your FastAPI app (adjust path if your main app is different)
from backend.app.main import app

client = TestClient(app)

# Helpers: stub tokens / sample headers
SAMPLE_JWT = "Bearer testtoken123"  # your get_current_user must accept or be monkeypatched
SAMPLE_API_KEY = "X-API-Key: test-apikey"

# ---------- Fixtures to monkeypatch services ----------
@pytest.fixture(autouse=True)
def patches(monkeypatch):
    # stub reserve_and_deduct to return a fake reserve tx dict or raise for insufficient funds
    def fake_reserve_and_deduct(user_id, amount, reference=None, team_id=None):
        # if amount is large, simulate insufficient
        if float(amount) > 10000:
            from fastapi import HTTPException
            raise HTTPException(status_code=402, detail="insufficient_credits")
        return {"balance_after": 1000.0, "transaction_id": 123}

    monkeypatch.setattr("backend.app.api.v1.decision_makers.reserve_and_deduct", fake_reserve_and_deduct, raising=False)
    monkeypatch.setattr("backend.app.api.v1.verification.reserve_and_deduct", fake_reserve_and_deduct, raising=False)
    monkeypatch.setattr("backend.app.api.v1.extractor.reserve_and_deduct", fake_reserve_and_deduct, raising=False)
    monkeypatch.setattr("backend.app.api.v1.bulk.reserve_and_deduct", fake_reserve_and_deduct, raising=False)

    # stub add_credits to return a tx dict
    def fake_add_credits(user_id, amount, reference=None):
        return {"balance_after": 2000.0, "transaction_id": 999}
    monkeypatch.setattr("backend.app.api.v1.decision_makers.add_credits", fake_add_credits, raising=False)
    monkeypatch.setattr("backend.app.api.v1.verification.add_credits", fake_add_credits, raising=False)
    monkeypatch.setattr("backend.app.api.v1.extractor.add_credits", fake_add_credits, raising=False)
    monkeypatch.setattr("backend.app.api.v1.bulk.add_credits", fake_add_credits, raising=False)

    # stub search_decision_makers to return N results
    def fake_search_decision_makers(domain=None, company_name=None, max_results=25, use_cache=True, caller_api_key=None):
        result = []
        for i in range(min(3, max_results)):
            result.append({"first_name": f"FN{i}", "last_name": f"LN{i}", "email": f"user{i}@{domain or 'example.com'}", "verified": True})
        return result
    monkeypatch.setattr("backend.app.api.v1.decision_makers.search_decision_makers", fake_search_decision_makers, raising=False)

    # stub verify_email_sync
    def fake_verify_email_sync(email, user_id=None):
        if "invalid" in email:
            return {"email": email, "status": "invalid"}
        return {"email": email, "status": "valid"}
    monkeypatch.setattr("backend.app.api.v1.verification.verify_email_sync", fake_verify_email_sync, raising=False)

    # stub extractor
    def fake_extract_url(url, parse_links=False):
        if "noemails" in url:
            return {"url": url, "emails": []}
        return {"url": url, "emails": ["a@b.com"]}
    monkeypatch.setattr("backend.app.api.v1.extractor.extract_url", fake_extract_url, raising=False)

    yield


# ---------- Tests ----------

def test_decision_makers_search_user_success():
    payload = {"domain":"example.com","max_results":3}
    headers = {"Authorization": SAMPLE_JWT}
    resp = client.post("/api/v1/decision-makers/search", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert data["returned_results"] == 3
    assert float(data["estimated_cost"]) >= 0.0

def test_decision_makers_search_team_refund_flow():
    payload = {"domain":"example.com","max_results":3,"team_id":1}
    headers = {"Authorization": SAMPLE_JWT}
    resp = client.post("/api/v1/decision-makers/search", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["returned_results"] <= payload["max_results"]
    assert "refund_amount" in data

def test_verification_single_refund_for_invalid():
    payload = {"email":"invalid@example.com"}
    headers = {"Authorization": SAMPLE_JWT}
    resp = client.post("/api/v1/verify/single", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["status"] == "invalid"
    assert data["refund_amount"] > 0

def test_extractor_single_no_emails_refund():
    payload = {"url":"https://site.com/noemails"}
    headers = {"Authorization": SAMPLE_JWT}
    resp = client.post("/api/v1/extractor/single", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"]["emails"] == []
    assert data["refund_amount"] > 0

def test_bulk_submit_requires_file_and_reserves(monkeypatch):
    # create an in-memory CSV file bytes
    csv_bytes = b"user1@example.com\nuser2@example.com\n"
    files = {"file": ("emails.csv", csv_bytes, "text/csv")}
    headers = {"Authorization": SAMPLE_JWT}
    resp = client.post("/api/v1/bulk/submit", files=files, headers=headers)
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "job_id" in data
    assert data["total"] >= 1

# backend/tests/test_team_billing.py
import pytest
from decimal import Decimal
from backend.app.db import SessionLocal, init_db
from backend.app.models.user import User
from backend.app.models.team import Team
from backend.app.services.team_billing_service import add_team_credits, get_team_balance, reserve_and_deduct_team, capture_team_reservation

@pytest.fixture(scope="module")
def db_setup():
    init_db()
    db = SessionLocal()
    yield db
    db.close()

def test_team_topup_and_reserve(db_setup):
    db = db_setup
    u = User(email="owner@example.com", hashed_password="x", is_active=True)
    db.add(u); db.commit(); db.refresh(u)

    # create team
    t = Team(name=f"test-team-{u.id}", owner_id=u.id, credits=0)
    db.add(t); db.commit(); db.refresh(t)

    # topup team
    res = add_team_credits(t.id, Decimal("100.0"), reference="test_topup")
    assert res["balance_after"] >= 100.0

    # reserve
    r = reserve_and_deduct_team(t.id, Decimal("10.0"), reference="test_reserve", job_id="job-test")
    assert "reservation_id" in r

    # capture reservation
    tx = capture_team_reservation(r["reservation_id"], type_="test_charge", reference="test_capture")
    assert "transaction_id" in tx

    # final balance: <= 90
    b = get_team_balance(t.id)
    assert Decimal(b) <= Decimal("90.0")


