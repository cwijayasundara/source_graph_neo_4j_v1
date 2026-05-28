from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_post_brd_starts_background_task():
    from code_context_graph.api import app

    with patch("code_context_graph.api.generate_brd") as gen_mock:
        gen_mock.return_value = MagicMock(
            brd_id="abc", rating=MagicMock(value="high"), attempts=1,
            weighted_score=4.5, version=1, html_path="/tmp/x.html",
            created_at=MagicMock(isoformat=lambda: "2026-01-01T00:00:00Z"),
            strategy=MagicMock(value="single_shot"),
        )
        client = TestClient(app)
        resp = client.post("/api/repos/acme-app/brd")
        assert resp.status_code in (200, 202)
        data = resp.json()
        assert "status" in data


def test_get_brd_returns_latest_summary():
    from code_context_graph.api import app, get_client

    with patch.object(get_client(), "run") as run_mock:
        run_mock.return_value = [{
            "b": {
                "id": "abc", "version": 2, "rating": "high",
                "attempts": 1, "weighted_score": 4.5,
                "created_at": "2026-01-01T00:00:00Z",
                "model": "claude-opus-4-7[1m]", "strategy": "single_shot",
                "attempt_history": "[]",
            }
        }]
        client = TestClient(app)
        resp = client.get("/api/repos/acme-app/brd")
        assert resp.status_code == 200
        assert resp.json()["rating"] == "high"


def test_get_brd_html_returns_html_content_type():
    from code_context_graph.api import app, get_client

    with patch.object(get_client(), "run") as run_mock:
        run_mock.return_value = [{"html": "<html><body>ok</body></html>"}]
        client = TestClient(app)
        resp = client.get("/api/repos/acme-app/brd/abc-123/html")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "<body>ok</body>" in resp.text
