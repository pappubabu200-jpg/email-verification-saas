import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from backend.app.tasks.bulk_tasks import process_bulk_job_task
from backend.app.models.bulk_job import BulkJob


@pytest.fixture
def mock_db(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.obj = None

        def query(self, *_):
            return self

        def filter(self, *_):
            return self

        def with_for_update(self, *_):
            return self

        def first(self):
            self.obj = BulkJob(
                job_id="J1",
                status="pending",
                input_path="/tmp/test.csv",
            )
            return self.obj

        def add(self, *_): pass
        def commit(self): pass
        def refresh(self, *_): pass
        def close(self): pass

    monkeypatch.setattr(
        "backend.app.tasks.bulk_tasks.SessionLocal",
        lambda: FakeDB(),
    )


@patch("backend.app.tasks.bulk_tasks.process_bulk_job")
def test_bulk_job_task_success(mock_process):
    mock_process.return_value = True
    out = process_bulk_job_task("J1", 5.2)
    assert out["ok"] is True
    assert out["job_id"] == "J1"
