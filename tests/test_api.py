"""Smoke test that the FastAPI app can be imported and routes are registered."""
from __future__ import annotations


def test_app_routes_registered() -> None:
    from code_context_graph.api import app

    paths = [route.path for route in app.routes]
    assert "/api/repos" in paths
    assert "/api/repos/clone" in paths
    assert "/api/repos/local" in paths
    assert "/api/graph" in paths
    assert "/api/query" in paths
    assert "/api/ask" in paths
    assert "/api/search" in paths
    assert "/api/stats" in paths


def test_get_graph_uses_property_maps_for_optional_node_fields(monkeypatch) -> None:
    from code_context_graph import api

    class FakeClient:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def run(self, query: str, **params):
            self.queries.append(query)
            if "properties(e) AS entity" in query:
                return [
                    {
                        "entity": {
                            "qualified_name": "app.main",
                            "simple_name": "main",
                            "kind": "Module",
                            "file_path": "app/main.py",
                        }
                    }
                ]
            return []

    client = FakeClient()
    monkeypatch.setattr(api, "get_client", lambda: client)

    graph = api.get_graph(repo="owner/repo")

    assert graph == {
        "nodes": [
            {
                "id": "app.main",
                "name": "main",
                "kind": "Module",
                "file": "app/main.py",
                "complexity": None,
                "signature": None,
                "docstring": None,
                "is_async": None,
                "layer": None,
                "summary": None,
            }
        ],
        "links": [],
    }
    assert "e.semantic_layer" not in client.queries[0]
    assert "e.semantic_summary" not in client.queries[0]
