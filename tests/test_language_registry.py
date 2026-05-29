"""Repo-level language extractor registry. Pure, no Neo4j/JVM."""
from __future__ import annotations

from pathlib import Path

import pytest

from code_context_graph import language_registry as reg
from code_context_graph.language_registry import (
    register_repo_extractor,
    run_repo_extractors,
)
from code_context_graph.models import CodeEntity, EntityKind, ParseResult


@pytest.fixture
def isolated_registry():
    """Save/restore the global registry so these tests don't disturb the
    COBOL extractor that gets registered on package import."""
    saved = list(reg._extractors)
    reg._extractors.clear()
    yield
    reg._extractors[:] = saved


def test_register_and_run(isolated_registry):
    pr = ParseResult(file_path="X", entities=[], relationships=[])
    register_repo_extractor(lambda root: [pr])
    out = run_repo_extractors(Path("."))
    assert out == [pr]


def test_runs_extractors_in_registration_order(isolated_registry):
    register_repo_extractor(lambda r: [ParseResult(file_path="a", entities=[], relationships=[])])
    register_repo_extractor(lambda r: [ParseResult(file_path="b", entities=[], relationships=[])])
    out = run_repo_extractors(Path("."))
    assert [p.file_path for p in out] == ["a", "b"]


def test_run_with_no_extractors_returns_empty(isolated_registry):
    assert run_repo_extractors(Path(".")) == []
