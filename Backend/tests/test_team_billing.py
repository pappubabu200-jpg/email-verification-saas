
# backend/tests/test_team_billing.py
import os
import tempfile
import pytest
from decimal import Decimal
from backend.app.db import init_db, Base, engine, SessionLocal
from backend.app.models.user import User
from backend.app.models.team import Team
from backend.app.models.team_member import TeamMember
from backend.app.services.team_billing_service import add_team_credits, reserve_and_deduct_team, capture_reservation_and_charge_team, get_team_balance

@pytest.fixture(scope="module")
def db_setup():
    # use SQLite temporary DB for tests
    tmp = tempfile.NamedTemporaryFile(delete=False)
    url = f"sqlite:///{tmp.name}"
    # patch config if needed (or ensure app.db uses engine bound to this in tests)
    # initialize DB
    Base.metadata.create_all(bind=engine)
    yield
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception:
        pass

def test_team_flow(db_setup):
    db = SessionLocal()
    try:
        # create user and team
        user = User(email="owner@example.com", hashed_password="x", is_active=True)
        db.add(user); db.commit(); db.refresh(user)
        team = Team(name="TestTeam", owner_id=user.id, credits=100)
        db.add(team); db.commit(); db.refresh(team)
        # add member
        member = TeamMember(team_id=team.id, user_id=user.id, role="owner", active=True)
        db.add(member); db.commit()
        # add team credits
        res = add_team_credits(team.id, Decimal("50"), reference="unit-test-topup")
        assert "balance_after" in res
        # reserve credits
        r = reserve_and_deduct_team(team.id, Decimal("20"), reference="reserve-test", job_id="job-test-1")
        assert r["reserved_amount"] == 20.0 or float(r["reserved_amount"]) == 20.0
        # capture reservation
        tx = capture_reservation_and_charge_team(r["reservation_id"], type_="team_charge_test", reference="capture-test")
        assert "tx_id" in tx
    finally:
        db.close()
