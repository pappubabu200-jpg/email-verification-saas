# backend/scripts/simulate_bulk_job.py
"""
Run this script to simulate:
- create user
- create team
- topup team
- upload a small CSV to MinIO
- create BulkJob row
- run worker function process_bulk_task synchronously
"""
import os, io, uuid, json
from decimal import Decimal
from backend.app.db import SessionLocal, init_db
from backend.app.models.user import User
from backend.app.models.team import Team
from backend.app.models.bulk_job import BulkJob
from backend.app.services.minio_client import put_bytes, MINIO_BUCKET, ensure_bucket
from backend.app.workers.bulk_tasks import process_bulk_task
from backend.app.services.team_billing_service import add_team_credits

def main():
    init_db()
    db = SessionLocal()
    try:
        # create user
        user = User(email=f"sim{uuid.uuid4().hex[:6]}@example.com", hashed_password="x", is_active=True)
        db.add(user); db.commit(); db.refresh(user)

        # create team
        team = Team(name=f"sim-team-{uuid.uuid4().hex[:6]}", owner_id=user.id, credits=0)
        db.add(team); db.commit(); db.refresh(team)

        # topup
        add_team_credits(team.id, Decimal("50.0"), reference="sim_topup")

        # minio upload
        ensure_bucket()
        csv_content = "a@example.com\nb@example.com\ninvalid\nc@example.com\n"
        object_name = f"sim_inputs/{user.id}-{uuid.uuid4().hex[:8]}.csv"
        put_bytes(object_name, csv_content.encode("utf-8"), content_type="text/csv")
        input_path = f"s3://{MINIO_BUCKET}/{object_name}"

        # create job
        job_id = f"bulk-sim-{uuid.uuid4().hex[:8]}"
        job = BulkJob(user_id=user.id, job_id=job_id, status="queued", input_path=input_path, total=3, webhook_url=None)
        db.add(job); db.commit(); db.refresh(job)

        # run worker synchronously
        print("Running worker sync for job:", job.job_id)
        process_bulk_task(job.job_id, float(0.0))
        print("done")

    finally:
        db.close()

if __name__ == "__main__":
    main()
