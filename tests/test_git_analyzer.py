from __future__ import annotations

from pathlib import Path

from git import GitCommandError

from code_context_graph.git_analyzer import GitAnalyzer


class FakeAuthor:
    name = "Ada Lovelace"
    email = "ada@example.test"


class FakeStats:
    files = {"src/good.py": {}, "README.md": {}}


class FakeCommit:
    author = FakeAuthor()

    def __init__(self, stats: FakeStats | Exception) -> None:
        self._stats = stats

    @property
    def stats(self) -> FakeStats:
        if isinstance(self._stats, Exception):
            raise self._stats
        return self._stats


class FakeRepo:
    def __init__(self, commits: list[FakeCommit]) -> None:
        self.commits = commits

    def iter_commits(self) -> list[FakeCommit]:
        return self.commits


def analyzer_with_commits(commits: list[FakeCommit]) -> GitAnalyzer:
    analyzer = GitAnalyzer.__new__(GitAnalyzer)
    analyzer.repo = FakeRepo(commits)
    return analyzer


def test_authors_skip_file_stats_when_commit_parent_is_unavailable() -> None:
    error = GitCommandError(["git", "diff"], 128, stderr="fatal: bad object parent")
    analyzer = analyzer_with_commits([FakeCommit(error), FakeCommit(FakeStats())])

    authors = analyzer.authors()

    assert len(authors) == 1
    assert authors[0].commit_count == 2
    assert authors[0].files_touched == ["src/good.py"]


def test_file_authors_skip_commits_with_unavailable_stats() -> None:
    error = GitCommandError(["git", "diff"], 128, stderr="fatal: bad object parent")
    analyzer = analyzer_with_commits([FakeCommit(error), FakeCommit(FakeStats())])

    assert analyzer.file_authors() == {"src/good.py": ["ada@example.test"]}


def test_co_changes_skip_commits_with_unavailable_stats() -> None:
    error = GitCommandError(["git", "diff"], 128, stderr="fatal: bad object parent")
    analyzer = analyzer_with_commits([FakeCommit(error), FakeCommit(FakeStats())])

    assert analyzer.co_changes() == []
