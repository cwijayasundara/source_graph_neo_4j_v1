from __future__ import annotations

from typing import Any

from code_context_graph.repo_manager import RepoManager


class FakeClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.queries: list[str] = []
        self.params: list[dict[str, Any]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        self.params.append(params)
        return self.rows


def test_list_repos_uses_properties_map_for_optional_fields() -> None:
    client = FakeClient([{"repo": {"slug": "owner/repo"}}])

    repos = RepoManager(client).list_repos()

    assert repos == [
        {
            "slug": "owner/repo",
            "url": None,
            "files_parsed": 0,
            "entities": 0,
            "relationships": 0,
            "authors": 0,
            "ingested_at": None,
            "local_path": None,
        }
    ]
    query = client.queries[0]
    assert "properties(r) AS repo" in query
    assert "r.url" not in query
    assert "r.files_parsed" not in query
    assert "r.entities" not in query
    assert "r.relationships" not in query
    assert "r.authors" not in query
    assert "r.ingested_at" not in query


def test_get_repo_normalizes_missing_optional_fields() -> None:
    client = FakeClient([{"repo": {"slug": "owner/repo", "url": "https://example.test/repo"}}])

    repo = RepoManager(client).get("owner/repo")

    assert repo == {
        "slug": "owner/repo",
        "url": "https://example.test/repo",
        "files_parsed": 0,
        "entities": 0,
        "relationships": 0,
        "authors": 0,
        "ingested_at": None,
        "local_path": None,
    }
