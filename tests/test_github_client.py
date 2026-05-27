"""Tests for GitHub URL parsing — no network or Neo4j needed."""
from __future__ import annotations

from pathlib import Path

import pytest

from code_context_graph.github_client import clone_repo, parse_github_url, repo_slug


def test_parse_https_url() -> None:
    owner, name = parse_github_url("https://github.com/neo4j-labs/create-context-graph")
    assert owner == "neo4j-labs"
    assert name == "create-context-graph"


def test_parse_https_with_git_suffix() -> None:
    owner, name = parse_github_url("https://github.com/owner/repo.git")
    assert owner == "owner"
    assert name == "repo"


def test_parse_repo_name_with_dot_and_git_suffix() -> None:
    owner, name = parse_github_url(
        "https://github.com/cwijayasundara/neo_4j_context_graphs_v1.0.git"
    )
    assert owner == "cwijayasundara"
    assert name == "neo_4j_context_graphs_v1.0"


def test_parse_ssh_url() -> None:
    owner, name = parse_github_url("git@github.com:owner/my-repo.git")
    assert owner == "owner"
    assert name == "my-repo"


def test_parse_trailing_slash() -> None:
    owner, name = parse_github_url("https://github.com/owner/repo/")
    assert owner == "owner"
    assert name == "repo"


def test_parse_invalid_url_raises() -> None:
    with pytest.raises(ValueError, match="Not a valid GitHub URL"):
        parse_github_url("https://gitlab.com/owner/repo")


def test_repo_slug() -> None:
    assert repo_slug("https://github.com/neo4j-labs/create-context-graph") == "neo4j-labs/create-context-graph"


def test_clone_repo_defaults_to_source_code_to_analyse(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_clone_from(url: str, dest: str, **kwargs: object) -> None:
        captured["url"] = url
        captured["dest"] = Path(dest)
        captured["kwargs"] = kwargs

    monkeypatch.setattr("code_context_graph.github_client.Repo.clone_from", fake_clone_from)

    path = clone_repo("https://github.com/owner/repo.git")

    assert path.parts[-3:] == ("source_code_to_analyse", "owner", "repo")
    assert captured["dest"] == path
    assert captured["kwargs"] == {"depth": 1}
