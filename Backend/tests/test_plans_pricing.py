# backend/tests/test_plans_pricing.py
import pytest
from fastapi.testclient import TestClient

# import your FastAPI app
try:
    from backend.app.main import app
except Exception:
    # fallback if main location differs
    from backend.app import main as mainmod
    app = getattr(mainmod, "app")

client = TestClient(app)

def test_get_pricing():
    resp = client.get("/api/v1/pricing/")
    assert resp.status_code in (200, 501)
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, dict)

def test_list_plans():
    resp = client.get("/api/v1/plans/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # at least default items present
    assert any(p.get("name") for p in data)
