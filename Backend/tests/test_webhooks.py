
import pytest
from unittest.mock import patch
from backend.app.tasks.webhook_tasks import send_webhook


@patch("backend.app.tasks.webhook_tasks.requests.post")
def test_webhook_success(mock_post):
    mock_post.return_value.status_code = 200
    out = send_webhook.run("http://example.com", {"x": 1})
    assert out["ok"] is True


@patch("backend.app.tasks.webhook_tasks.requests.post")
def test_webhook_retry_on_400(mock_post):
    mock_post.return_value.status_code = 400

    with pytest.raises(Exception):
        send_webhook.run("http://example.com", {"x": 1})
