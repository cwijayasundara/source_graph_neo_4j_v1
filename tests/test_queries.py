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


def test_name_matching_is_case_insensitive() -> None:
    # COBOL names are stored UPPERCASE; a user typing lowercase must still match.
    client = FakeClient()

    CodeGraphQueries(client).what_does_it_call("payroll")

    query, params = client.calls[0]
    assert "toLower(caller.simple_name) = toLower($name)" in query
    assert "toLower(caller.qualified_name) = toLower($name)" in query
    assert params == {"name": "payroll"}


def test_suggest_entities_uses_case_insensitive_prefix() -> None:
    client = FakeClient()

    CodeGraphQueries(client).suggest_entities("pay")

    query, params = client.calls[0]
    assert "toLower(e.simple_name) STARTS WITH toLower($prefix)" in query
    assert "toLower(e.qualified_name) STARTS WITH toLower($prefix)" in query
    assert params == {"prefix": "pay", "limit": 10}


def test_suggest_entities_scopes_to_repo_and_limit() -> None:
    client = FakeClient()

    CodeGraphQueries(client).suggest_entities("pay", repo="owner/repo", limit=5)

    query, params = client.calls[0]
    assert "properties(e).repo = $repo" in query
    assert params == {"prefix": "pay", "repo": "owner/repo", "limit": 5}
