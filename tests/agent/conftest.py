from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest


class SeededNeo4j:
    """Fake Neo4jClient that answers run() from a list of (predicate, rows) rules.

    Each rule is (match_fn, rows): the first rule whose match_fn(query, params)
    returns True supplies the rows. Lets tests script graph responses precisely.
    """

    def __init__(self) -> None:
        self.rules: list[tuple[Callable[[str, dict], bool], list[dict]]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def when(self, match_fn: Callable[[str, dict], bool], rows: list[dict]) -> "SeededNeo4j":
        self.rules.append((match_fn, rows))
        return self

    def run(self, query: str, **params: Any) -> list[dict]:
        self.calls.append((query, params))
        for match_fn, rows in self.rules:
            if match_fn(query, params):
                return rows
        return []


@pytest.fixture
def seeded() -> SeededNeo4j:
    return SeededNeo4j()


@pytest.fixture
def repo_tree(tmp_path: Path) -> Path:
    """A tiny on-disk repo for source-slice tests."""
    f = tmp_path / "src" / "mod.py"
    f.parent.mkdir(parents=True)
    f.write_text("line1\nline2\nline3\nline4\nline5\n")
    return tmp_path
