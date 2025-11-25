from backend.app.services.bulk_processor import CSVWriterThread
import queue
import os

def test_csv_writer(tmp_path):
    out_file = tmp_path / "out.csv"
    q = queue.Queue()

    writer = CSVWriterThread(str(out_file), q, ["email", "status"])
    writer.start()

    q.put(("a@b.com", "valid"))
    q.put(("c@d.com", "invalid"))
    q.put(None)  # sentinel

    writer.join(timeout=3)

    assert out_file.exists()
    data = out_file.read_text()
    assert "a@b.com" in data
    assert "c@d.com" in data
