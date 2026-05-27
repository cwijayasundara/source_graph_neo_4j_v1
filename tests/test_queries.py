from __future__ import annotations

from typing import Any

from code_context_graph.queries import CodeGraphQueries


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> list[dict]:
        self.calls.append((query, params))
        return []


def test_complex_functions_can_be_scoped_to_repo() -> None:
    client = FakeClient()

    CodeGraphQueries(client).complex_functions(10, repo="owner/repo")

    query, params = client.calls[0]
    assert "properties(e).repo = $repo" in query
    assert params == {"min_complexity": 10, "repo": "owner/repo"}


def test_what_does_it_call_can_be_scoped_to_repo() -> None:
    client = FakeClient()

    CodeGraphQueries(client).what_does_it_call("handle_message", repo="owner/repo")

    query, params = client.calls[0]
    assert "properties(caller).repo = $repo" in query
    assert params == {"name": "handle_message", "repo": "owner/repo"}
