from __future__ import annotations

from typing import Any

import pytest


class FakeNeo4jClient:
    """Records run() calls and returns scripted results."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._scripted: list[list[dict]] = []

    def script(self, *results: list[dict]) -> None:
        self._scripted = list(results)

    def run(self, query: str, **params: Any) -> list[dict]:
        self.calls.append((query, params))
        if self._scripted:
            return self._scripted.pop(0)
        return []


@pytest.fixture
def fake_client() -> FakeNeo4jClient:
    return FakeNeo4jClient()
